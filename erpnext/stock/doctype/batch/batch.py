# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname, revert_series_if_last
from frappe.utils import cint, flt, get_link_to_form
from frappe.utils.data import add_days
from frappe.utils.jinja import render_template
from six import text_type


class UnableToSelectBatchError(frappe.ValidationError):
	pass


def get_name_from_hash():
	"""
	Get a name for a Batch by generating a unique hash.
	:return: The hash that was generated.
	"""
	temp = None
	while not temp:
		temp = frappe.generate_hash()[:7].upper()
		if frappe.db.exists("Batch", temp):
			temp = None

	return temp


def batch_uses_naming_series():
	"""
	Verify if the Batch is to be named using a naming series
	:return: bool
	"""
	use_naming_series = cint(frappe.db.get_single_value("Stock Settings", "use_naming_series"))
	return bool(use_naming_series)


def _get_batch_prefix():
	"""
	Get the naming series prefix set in Stock Settings.

	It does not do any sanity checks so make sure to use it after checking if the Batch
	is set to use naming series.
	:return: The naming series.
	"""
	naming_series_prefix = frappe.db.get_single_value("Stock Settings", "naming_series_prefix")
	if not naming_series_prefix:
		naming_series_prefix = "BATCH-"

	return naming_series_prefix


def _make_naming_series_key(prefix):
	"""
	Make naming series key for a Batch.

	Naming series key is in the format [prefix].[#####]
	:param prefix: Naming series prefix gotten from Stock Settings
	:return: The derived key. If no prefix is given, an empty string is returned
	"""
	if not text_type(prefix):
		return ""
	else:
		return prefix.upper() + ".#####"


def get_batch_naming_series():
	"""
	Get naming series key for a Batch.

	Naming series key is in the format [prefix].[#####]
	:return: The naming series or empty string if not available
	"""
	series = ""
	if batch_uses_naming_series():
		prefix = _get_batch_prefix()
		key = _make_naming_series_key(prefix)
		series = key

	return series


class Batch(Document):
	def autoname(self):
		"""Generate random ID for batch if not specified"""
		if not self.batch_id:
			create_new_batch, batch_number_series = frappe.db.get_value(
				"Item", self.item, ["create_new_batch", "batch_number_series"]
			)

			if create_new_batch:
				if batch_number_series:
					self.batch_id = make_autoname(batch_number_series, doc=self)
				elif batch_uses_naming_series():
					self.batch_id = self.get_name_from_naming_series()
				else:
					self.batch_id = get_name_from_hash()
			else:
				frappe.throw(_("Batch ID is mandatory"), frappe.MandatoryError)

		self.name = self.batch_id

	def onload(self):
		self.image = frappe.db.get_value("Item", self.item, "image")

	def after_delete(self):
		revert_series_if_last(get_batch_naming_series(), self.name)

	def validate(self):
		self.item_has_batch_enabled()

	def item_has_batch_enabled(self):
		if frappe.db.get_value("Item", self.item, "has_batch_no") == 0:
			frappe.throw(_("The selected item cannot have Batch"))

	def before_save(self):
		has_expiry_date, shelf_life_in_days = frappe.db.get_value(
			"Item", self.item, ["has_expiry_date", "shelf_life_in_days"]
		)
		if not self.expiry_date and has_expiry_date and shelf_life_in_days:
			self.expiry_date = add_days(self.manufacturing_date, shelf_life_in_days)

		if has_expiry_date and not self.expiry_date:
			frappe.throw(
				msg=_("Please set {0} for Batched Item {1}, which is used to set {2} on Submit.").format(
					frappe.bold("Shelf Life in Days"),
					get_link_to_form("Item", self.item),
					frappe.bold("Batch Expiry Date"),
				),
				title=_("Expiry Date Mandatory"),
			)

	def get_name_from_naming_series(self):
		"""
		Get a name generated for a Batch from the Batch's naming series.
		:return: The string that was generated.
		"""
		naming_series_prefix = _get_batch_prefix()
		# validate_template(naming_series_prefix)
		naming_series_prefix = render_template(str(naming_series_prefix), self.__dict__)
		key = _make_naming_series_key(naming_series_prefix)
		name = make_autoname(key)

		return name


@frappe.whitelist()
def get_batch_qty(
	batch_no=None, warehouse=None, item_code=None, posting_date=None, posting_time=None
):
	"""Returns batch actual qty if warehouse is passed,
	        or returns dict of qty by warehouse if warehouse is None

	The user must pass either batch_no or batch_no + warehouse or item_code + warehouse

	:param batch_no: Optional - give qty for this batch no
	:param warehouse: Optional - give qty for this warehouse
	:param item_code: Optional - give qty for this item"""

	out = 0
	if batch_no and warehouse:
		cond = ""
		if posting_date and posting_time:
			cond = " and timestamp(posting_date, posting_time) <= timestamp('{0}', '{1}')".format(
				posting_date, posting_time
			)

		out = float(
			frappe.db.sql(
				"""select sum(actual_qty)
			from `tabStock Ledger Entry`
			where is_cancelled = 0 and warehouse=%s and batch_no=%s {0}""".format(
					cond
				),
				(warehouse, batch_no),
			)[0][0]
			or 0
		)

	if batch_no and not warehouse:
		out = frappe.db.sql(
			"""select warehouse, sum(actual_qty) as qty
			from `tabStock Ledger Entry`
			where is_cancelled = 0 and batch_no=%s
			group by warehouse""",
			batch_no,
			as_dict=1,
		)

	if not batch_no and item_code and warehouse:
		out = frappe.db.sql(
			"""select batch_no, sum(actual_qty) as qty
			from `tabStock Ledger Entry`
			where is_cancelled = 0 and item_code = %s and warehouse=%s
			group by batch_no""",
			(item_code, warehouse),
			as_dict=1,
		)

	return out


@frappe.whitelist()
def get_batches_by_oldest(item_code, warehouse):
	"""Returns the oldest batch and qty for the given item_code and warehouse"""
	batches = get_batch_qty(item_code=item_code, warehouse=warehouse)
	batches_dates = [
		[batch, frappe.get_value("Batch", batch.batch_no, "expiry_date")] for batch in batches
	]
	batches_dates.sort(key=lambda tup: tup[1])
	return batches_dates


@frappe.whitelist()
def split_batch(batch_no, item_code, warehouse, qty, new_batch_id=None, new_batch_expiry=None):
	"""Split the batch into a new batch"""
	batch = frappe.get_doc(dict(doctype="Batch", item=item_code, batch_id=new_batch_id, expiry_date=new_batch_expiry)).insert()

	company = frappe.db.get_value(
		"Stock Ledger Entry",
		dict(item_code=item_code, batch_no=batch_no, warehouse=warehouse),
		["company"],
	)

	stock_entry = frappe.get_doc(
		dict(
			doctype="Stock Entry",
			purpose="Repack",
			company=company,
			items=[
				dict(item_code=item_code, qty=float(qty or 0), s_warehouse=warehouse, batch_no=batch_no),
				dict(item_code=item_code, qty=float(qty or 0), t_warehouse=warehouse, batch_no=batch.name),
			],
		)
	)
	stock_entry.set_stock_entry_type()
	stock_entry.insert()
	stock_entry.submit()

	return batch.name


def set_batch_nos(doc, warehouse_field, throw=False, child_table="items"):
	"""Automatically select `batch_no` for outgoing items in item table"""
	for d in doc.get(child_table):
		qty = d.get("stock_qty") or d.get("transfer_qty") or d.get("qty") or 0
		warehouse = d.get(warehouse_field, None)
		if warehouse and qty > 0 and frappe.db.get_value("Item", d.item_code, "has_batch_no"):
			if not d.batch_no:
				d.batch_no = get_batch_no(d.item_code, warehouse, qty, throw, d.serial_no)
			else:
				batch_qty = get_batch_qty(batch_no=d.batch_no, warehouse=warehouse)
				if flt(batch_qty, d.precision("qty")) < flt(qty, d.precision("qty")):
					frappe.throw(
						_(
							"Row #{0}: The batch {1} has only {2} qty. Please select another batch which has {3} qty available or split the row into multiple rows, to deliver/issue from multiple batches"
						).format(d.idx, d.batch_no, batch_qty, qty)
					)


@frappe.whitelist()
def get_batch_no(item_code, warehouse, qty=1, throw=False, serial_no=None, cur_batch_no=None):
	"""
	Get batch number using First Expiring First Out method.
	:param item_code: `item_code` of Item Document
	:param warehouse: name of Warehouse to check
	:param qty: quantity of Items
	:return: String represent batch number of batch with sufficient quantity else an empty String
	"""
	from frappe.utils import add_months, getdate, today
	today_date = getdate(today())
	alert_date = add_months(today_date, int(frappe.get_value("Item", item_code, "shortdated_timeframe_in_months")))


	batch_no = None
	batches = get_batches(item_code, warehouse, qty, throw, serial_no)

	## Filtered out the batch so that only batch have actual qty
	batches = list(filter(lambda batch : batch.qty > 0, batches)) 

	found = False
	shortdated_available = False
	for batch in batches:
		if batch.expiry_date and (alert_date > getdate(batch.expiry_date)) and not cur_batch_no:
			shortdated_available = True
		
		if found == True:
			continue
		if cint(qty) <= cint(batch.qty):
			if not batch_no:
				batch_no = batch.batch_id
				selected_expiry = batch.expiry_date
				batch_qty = batch.qty
				if not cur_batch_no:
					found = True
			if cur_batch_no == batch.batch_id:
				batch_no = cur_batch_no
				batch_qty = batch.qty
				selected_expiry = batch.expiry_date
				found = True

	if not batch_no:
		only_zero = True
		for batch in batches:
			if batch.qty != 0:
				only_zero = False
				break
		if only_zero:
			return
		table_html = ""
		if batches:
			table_html = """<table class="table table-striped table-bordered">
			<tr>
				<th>Batch ID</th>
				<th>Qty In Stock</th>
				<th>Expiry Date</th>
			</tr>"""
			for batch in batches:
				if batch.expiry_date and (alert_date > getdate(batch.expiry_date)):
					expiry = f"""<td  style="color: red;">{batch.expiry_date}</td>"""
				elif batch.expiry_date:
					expiry = f"""<td>{batch.expiry_date}</td>"""
				else:
					expiry = f"""<td  style="color: red;">None</td>"""
				table_html += f"""<tr>
					<td>{batch.batch_id}</td>
					<td>{batch.qty}</td>
					{expiry}
				</tr>"""
			table_html += "</table>"
		panels = f"""
			<div class="panel panel-default">
				<div class="panel-heading" style="text-align:center"><h3>Batch Selection for: { item_code }</h3></div>
				<div class="panel-body">
					<p>The entered qty is {frappe.bold(qty)}. Please manually select a Batch for Item { frappe.bold(item_code) }. Or you might want to split this item to more rows with different batch!</p>
			</div>
		"""
		final_html = panels + table_html
		# frappe.msgprint(final_html)
		frappe.response.content = final_html
		frappe.response.dialog_type = "multi"
		if throw:
			#TODO: Issue raised here
			raise UnableToSelectBatchError
	else:
		if selected_expiry and (alert_date > getdate(selected_expiry)):
			# frappe.msgprint("Warning: Batch {0} for Item {1} will expire in less than 6 months. Expiry date: <strong>{2}</strong>".format(batch.batch_id, item_code, batch.expiry_date))
			frappe.response.content = get_expiry_content(batch_no, batch_qty, selected_expiry, item_code)
			frappe.response.shortdated = 1
			frappe.response.dialog_type = "shortdated"
		else:
			if shortdated_available:
				frappe.response.content = get_longdated_content(batches, batch_no, item_code, alert_date, getdate)
				frappe.response.dialog_type = "longdated"
	return batch_no


def get_longdated_content(batches, batch_no, item_code, alert_date, getdate):
	table_html = """<table class="table table-striped table-bordered">
	<tr>
		<th>Batch ID</th>
		<th>Qty In Stock</th>
		<th>Expiry Date</th>
	</tr>"""
	for batch in batches:
		if batch.expiry_date and (alert_date > getdate(batch.expiry_date)):
			expiry = f"""<td  style="color: red;">{batch.expiry_date}</td>"""
		elif batch.expiry_date:
			expiry = f"""<td>{batch.expiry_date}</td>"""
		else:
			expiry = f"""<td  style="color: red;">None</td>"""
		table_html += f"""<tr>
			<td>{batch.batch_id}</td>
			<td>{batch.qty}</td>
			{expiry}
		</tr>"""
	table_html += "</table>"
	panels = f"""
		<div class="panel panel-default" style="text-align: center;">
			<div class="panel-heading" style="text-align:center"><h3 style="color: green;">ShortDated Batches Available for: { item_code }</h3></div>
			<div class="panel-body">
				<p>The batch <b>{batch_no}</b> currently selected is a long dated batch but there exists shortdated batches within our system. <br> Please confirm that this is correct and if not please select a batch that is short-dated.</p>
		</div>
	"""
	return table_html + panels

def get_expiry_content(batch_id, qty, expiry_date, item_code):
	table_html = f"""<table class="table table-striped table-bordered">
		<tr>
			<th>Batch ID</th>
			<th>Qty In Stock</th>
			<th >Expiry Date</th>
		</tr> 
		<tr>
			<td>{batch_id}</td>
			<td>{qty}</td>
			<td style="color: red;">{expiry_date}</td>
		</tr>"""
	table_html += "</table>"
	panels = f"""
		<div class="panel panel-default" style="text-align: center;">
			<div class="panel-heading" style="text-align:center"><h3 style="color: red;">ShortDated Batch selected for: { item_code }</h3></div>
			<div class="panel-body">
				<p>The batch {batch_id} is a short dated batch. <br> Please confirm that this is correct and if not please select a batch that is not short-dated .</p>
		</div>
	"""
	return table_html + panels
def get_batches(item_code, warehouse, qty=1, throw=False, serial_no=None):
	from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

	cond = ""
	if serial_no and frappe.get_cached_value("Item", item_code, "has_batch_no"):
		serial_nos = get_serial_nos(serial_no)
		batch = frappe.get_all(
			"Serial No",
			fields=["distinct batch_no"],
			filters={"item_code": item_code, "warehouse": warehouse, "name": ("in", serial_nos)},
		)

		if not batch:
			validate_serial_no_with_batch(serial_nos, item_code)

		if batch and len(batch) > 1:
			return []

		cond = " and `tabBatch`.name = %s" % (frappe.db.escape(batch[0].batch_no))

	return frappe.db.sql(
		"""
		select batch_id, sum(`tabStock Ledger Entry`.actual_qty) as qty, expiry_date
		from `tabBatch`
			join `tabStock Ledger Entry` ignore index (item_code, warehouse)
				on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
		where `tabStock Ledger Entry`.item_code = %s and `tabStock Ledger Entry`.warehouse = %s
			and `tabStock Ledger Entry`.is_cancelled = 0
			and (`tabBatch`.expiry_date >= CURDATE() or `tabBatch`.expiry_date IS NULL) {0}
		group by batch_id
		order by `tabBatch`.expiry_date ASC, `tabBatch`.creation ASC
	""".format(
			cond
		),
		(item_code, warehouse),
		as_dict=True,
	)


def validate_serial_no_with_batch(serial_nos, item_code):
	if frappe.get_cached_value("Serial No", serial_nos[0], "item_code") != item_code:
		frappe.throw(
			_("The serial no {0} does not belong to item {1}").format(
				get_link_to_form("Serial No", serial_nos[0]), get_link_to_form("Item", item_code)
			)
		)

	serial_no_link = ",".join(get_link_to_form("Serial No", sn) for sn in serial_nos)

	message = "Serial Nos" if len(serial_nos) > 1 else "Serial No"
	frappe.throw(_("There is no batch found against the {0}: {1}").format(message, serial_no_link))


def make_batch(args):
	if frappe.db.get_value("Item", args.item, "has_batch_no"):
		args.doctype = "Batch"
		frappe.get_doc(args).insert().name


@frappe.whitelist()
def get_pos_reserved_batch_qty(filters):
	import json

	from frappe.query_builder.functions import Sum

	if isinstance(filters, str):
		filters = json.loads(filters)

	p = frappe.qb.DocType("POS Invoice").as_("p")
	item = frappe.qb.DocType("POS Invoice Item").as_("item")
	sum_qty = Sum(item.qty).as_("qty")

	reserved_batch_qty = (
		frappe.qb.from_(p)
		.from_(item)
		.select(sum_qty)
		.where(
			(p.name == item.parent)
			& (p.consolidated_invoice.isnull())
			& (p.status != "Consolidated")
			& (p.docstatus == 1)
			& (item.docstatus == 1)
			& (item.item_code == filters.get("item_code"))
			& (item.warehouse == filters.get("warehouse"))
			& (item.batch_no == filters.get("batch_no"))
		)
		.run()
	)

	flt_reserved_batch_qty = flt(reserved_batch_qty[0][0])
	return flt_reserved_batch_qty


@frappe.whitelist()
def allocate_batches_table(doc, item_code, warehouse, type_required, qty_required):
	from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
			get_pricing_rule_for_item
	)
	from erpnext.stock.get_item_details import get_price_list_rate_for
	from erpnext.accounts.doctype.pricing_rule.utils import (
		get_pricing_rules,
		get_product_discount_rule,
	)
	import datetime
	import json
	qty_required = float(qty_required)
	doc = json.loads(doc)
	price_list_rate = get_price_list_rate_for({"price_list":doc['selling_price_list'], 'item_code':item_code, "customer":doc['customer']},item_code)
	
	#Get batches and turn into dict
	def get_batch():
		batches = get_batches_by_oldest(item_code, warehouse)
		batches = [batch for batch in batches if batch[0]['qty'] > 0]
		batch_dict = {}
		for batch in batches:
			batch_date = batch[1]
			if batch_date < datetime.date.today() + datetime.timedelta(days=365):
				batch[0]['shortdated'] = 1
			else:
				batch[0]['shortdated'] = 0
			if type_required == "Longdated Only" and batch[0]['shortdated'] == 1:
				continue
			elif type_required == "Shortdated Only" and batch[0]['shortdated'] == 0:
				continue
			batch[0]['result_qty'] = 0
			batch[0]['org_qty'] = batch[0]['qty']
			batch_dict[batch[0]['batch_no']] = batch
		return batch_dict
	
	batch_dict = get_batch()
	
	items_from_table = []
	pricing_rules = []
	brand = None
	item_group = None
	doc['items'] = [i for i in doc['items'] if i.get('item_code')]
	pricing_rules = convert_to_set([i['pricing_rules'] for i in doc['items'] if i['item_code'] == item_code and ('ignore_pricing_rules' not in i or i['ignore_pricing_rules'] != 1) and i['pricing_rules']])
	pricing_rules = list(pricing_rules)
	pricing_rule_dict = {}
	if pricing_rules:
		sql = """
		SELECT name, min_qty, max_qty from `tabPricing Rule` where name IN %(data)s 
		"""
		pricing_rule_info = frappe.db.sql(sql, {'data':tuple(pricing_rules)}, as_dict=True)
		
		
		for rule in pricing_rule_info:
			pricing_rule_dict[rule['name']] = {'min_qty':rule['min_qty'],'max_qty':rule['max_qty']}
	qty_in_list = 0


	for i in doc['items']:
		if i['item_code'] == item_code:
			if 'batch_no' not in i:
				i['batch_no'] = ""
			if not brand:
				brand = i.get('brand')
			if not item_group:
				item_group = i.get('item_group')
			i['qty'] = float(i['qty']) 
			item = {
				'name': i['name'],
				'qty': i['qty'],
				'pricing_rules': i['pricing_rules'],
				'ignore_pricing_rule': doc['ignore_pricing_rule'],
				'brand': brand,
				'item_group': item_group,
				'rate': i['rate'],
				'discount_percentage': i['discount_percentage'],
				'ignore_pricing_rules': 0
			}
			item['batch_no'] = i['batch_no']
			if i['is_free_item'] == 0:
				add_to_list = False
				if 'batch_no' in i and i['batch_no']:
					if i['batch_no'] not in batch_dict:
						continue
					add_to_list = True
				elif (i['pricing_rules']):
					add_to_list = True
					for rule in json.loads(i['pricing_rules']):
						if pricing_rule_dict[rule]['max_qty'] > 0:
							if 'max_qty' not in item:
								item['max_qty'] = pricing_rule_dict[rule]['max_qty']
				if 'ignore_pricing_rules' in i:
					item['ignore_pricing_rules'] = i['ignore_pricing_rules']
					add_to_list = True
				if add_to_list:
					qty_in_list += i['qty']
					items_from_table.append(item)
			else:
				qty_required -= i['qty']
	items_from_table = sorted(items_from_table, key=lambda k: (k['batch_no'].lower(), k['qty']), reverse=True)
	results = []
	for key in batch_dict:
		if qty_required <= 0:
			break
		batches_gotten = batch_dict[key][0]

		batch_no = batches_gotten['batch_no']

		batch_qty = batches_gotten['qty']
		if batch_qty > 0:
			if batch_qty >= qty_required:
				row_qty = qty_required
				batch_qty -= qty_required
			else:
				row_qty = batch_qty
				batch_qty = 0
			results.append({
				'name':'new',
				'batch_no': batch_no,
				'available_qty': batches_gotten['org_qty'],
				'qty': row_qty,
				'ignore_pricing_rule': '0',
				'shortdated_batch': batches_gotten['shortdated'],
				'brand': brand,
				'item_group': item_group,
			})
			qty_required -= row_qty
		
		batches_gotten['qty'] = batch_qty

	for item in items_from_table:
		max_qty = float('inf')
		min_qty = 0
		if item['pricing_rules']:
			pricing_rules = json.loads(item['pricing_rules'])
			for rule in pricing_rules:
				pr_max_qty = pricing_rule_dict[rule]['max_qty']
				if pr_max_qty == 0:
					pr_max_qty = float('inf')
				max_qty = min(max_qty, pr_max_qty)
				pr_min_qty = pricing_rule_dict[rule]['max_qty']
				min_qty = max(min_qty, pr_min_qty)
		for i in range(len(results)):
			result = results[i]
			if result['name'] != 'new':
				continue 
			if not item['batch_no'] or batch_dict[item['batch_no']][0]['result_qty'] >= batch_dict[item['batch_no']][0]['org_qty']:
				if min_qty <= result['qty']:
					if max_qty >= result['qty']:
						result['name'] = item['name']
						batch_dict[result['batch_no']][0]['result_qty'] += result['qty']
						break
					else:
						item['qty'], result['qty']  = result['qty'], max_qty
						result['name'] = item['name']
						batch_dict[result['batch_no']][0]['result_qty'] += result['qty']
						results.append(result.copy())
						result['qty'] = item['qty'] - result['qty']
						result['name'] = 'new'
						break
					batch_dict[result['batch_no']][0]['result_qty'] += result['name'] 
	
	free_items = [i for i in doc['items'].copy() if i['item_code'] == item_code and i['is_free_item']]
	# doc['items'] = [i for i in doc['items'] if i['item_code'] != item_code ]
	free_item_results = {}
	for item in results:
		data = {}
		data.update(item)
		data.update({
			'item_code':item_code,
			'brand': brand ,
			'qty': item['qty'],
			'stock_qty': item['qty'],
			'transaction_type': 'selling',
			'price_list': doc['selling_price_list'],
			'customer_group': doc['customer_group'],
			'company': doc['company'],
			'conversion_rate': 1,
			'for_shopping_cart': True,
			'currency': frappe.db.get_value('Price List', doc['selling_price_list'], 'currency'),
			'customer': doc['customer'],
			'transaction_date': doc['posting_date'],
			'territory': doc['territory'],
			'ignore_pricing_rule': False if data['ignore_pricing_rule'] == '0' else True
		})
		pricing_rule = get_pricing_rule_for_item(frappe._dict(data), price_list_rate, frappe._dict(doc))
		if pricing_rule.get('price_or_product_discount') == 'Product':
			found = False
			pricing_rules = pricing_rule['pricing_rules']
			if pricing_rule['free_item_data'][0]['item_code'] == item_code:
				for i in free_items:
					if json.loads(pricing_rules) == json.loads(i['pricing_rules']):
						i.update({
							'rate': pricing_rule['free_item_data'][0]['rate'],
							'is_free_item': 'True',
							'pricing_rules': pricing_rules
						})
						if pricing_rules not in free_item_results or pricing_rule['free_item_data'][0]['qty'] > free_item_results[pricing_rules]['qty']:
							i['qty'] = pricing_rule['free_item_data'][0]['qty']
						else:
							i['qty'] = free_item_results[pricing_rules]['qty']
						free_item_results[pricing_rules] = i
						found = True
						break
				
				if not found:
					if pricing_rule['pricing_rules'] in free_item_results:
						if free_item_results[pricing_rule['pricing_rules']]['qty'] > pricing_rule['free_item_data'][0]['qty']:
							pricing_rule['free_item_data'][0]['qty'] = free_item_results[pricing_rule['pricing_rules']]['qty']
					free_item_results[pricing_rule['pricing_rules']] = {
						'item_code': item_code,
						'rate': pricing_rule['free_item_data'][0]['rate'],
						'qty': pricing_rule['free_item_data'][0]['qty'],
						'name':'new',
						'is_free_item': True,
						'pricing_rules': pricing_rule['pricing_rules']
					}
					
					free_item_data = free_item_results[pricing_rule['pricing_rules']]
					free_item_data['discount_percentage'] = ((price_list_rate-free_item_data['rate'])/price_list_rate)*100
		doc['items'].append(item)
	for pricing_rule in free_item_results:
		qty_required += free_item_results[pricing_rule]['qty']
	for key in batch_dict:
		if qty_required <= 0:
			break
		batches_gotten = batch_dict[key][0]
		
		batch_no = batches_gotten['batch_no']
		batch_qty = batches_gotten['qty']
		
		for key, value in free_item_results.items():
			if batch_qty <= 0:
				break
			if value['qty'] > batch_qty or 'done' in value:
				value['batch_no'] = batches_gotten['batch_no']
				value_copy = value.copy()
				value_copy['qty'] = batch_qty
				qty_required -= value_copy['qty']
				results.append(value_copy)
				value['qty'] = value['qty'] - batch_qty
			else:
				value['batch_no'] = batches_gotten['batch_no']
				batch_qty -= value['qty']
				qty_required -= value['qty']
				'is_free_item': True,
				'pricing_rules': i['pricing_rules']
			})
	actual_results = []

	
	for result in results:
		value = {
			'qty':result['qty'], 
			'name':result['name'], 
			'batch_no':result['batch_no'],
			'available_qty': batch_dict[result['batch_no']][0]['org_qty'],
			'shortdated': batch_dict[result['batch_no']][0]['shortdated']
		}
		if 'rate' in result:
			value['rate'] = result['rate']
		if 'pricing_rules' in result:
			value['pricing_rules'] = result['pricing_rules']
		if 'is_free_item' in result:
			value['is_free_item'] = result['is_free_item']
		if 'discount_percentage' in result:
			value['discount_percentage'] = result['discount_percentage']
		actual_results.append(value)
	
	return [actual_results, qty_required, backorder_items]

def convert_to_set(strings_list):
    import json
    result_set = set()
    for item in strings_list:
        try:results.append(value)
				free_item_results[key]['done'] = True
		batches_gotten['qty'] = batch_qty
	backorder_items = []
	for i in free_item_results:
		i = free_item_results[i]
		if 'done' not in i:
			backorder_items.append({
				'qty': i['qty'],
				'rate':i['rate'],
				
            # Try to convert the item from a string to a list
            item_list = json.loads(item)
            if isinstance(item_list, list):
                result_set.update(item_list)
        except ValueError:
            result_set.add(item)
    return result_set


def test():
	doc = '{"name":"NM-0129349","owner":"Administrator","creation":"2023-08-31 09:41:46.530248","modified":"2023-09-20 14:00:35.297203","modified_by":"Administrator","idx":0,"docstatus":0,"title":"Life Pharmacy Franklins","naming_series":"NM-.#######","customer":"10031","customer_name":"Life Pharmacy Franklins","email":"accounts@franklinspharmacy.co.nz","order_type":"Customer Order","order_source":"Backorder","is_pos":0,"is_consolidated":0,"is_return":0,"woocommerce_order":0,"is_debit_note":0,"update_billed_amount_in_sales_order":0,"company":"NaturalMeds","posting_date":"2023-09-20","posting_time":"14:00:35.559121","set_posting_time":0,"due_date":"2023-09-20","temporary_address":0,"cost_center":"NaturalMeds - Nm","delivery_provider":"NZ Couriers","po_no":"","payment_category":"Pay after Dispatch","transaction_date":"2023-08-31","po_date":"2023-08-31","credit_card_on_file":0,"customer_address":"10031-Billing","address_display":"\\nAccount: 10031,<br>\\n\\n48 Queen Street,\\n, Warkworth<br>\\nNew Zealand, 0910<br>\\n","contact_person":"CONTACT-07971","contact_display_name":"Example Contact  Current Primary ","contact_display":"double contact","contact_mobile":"","contact_email":"email@emailaddress.com","territory":"Auckland North/West/Northland","phone_number":"09 425 8014","shipping_address_name":"10031-Shipping","shipping_address":"\\nAccount: 10031,<br>\\n\\n42 Queen Street,\\n, Warkworth<br>\\nNew Zealand, 0910<br>\\n","company_address":"TOLL - AIR-Shipping","company_address_display":"\\nAccount: TOLL - AIR,<br>\\n\\nTOLL Warehouse Handler – St George CFS – AIR,\\n<br>1650 South Central Ave, DOCK 1-5 FOR AIR WINDOW 11, Compton<br>\\nCA<br>United States, 90220<br>\\n","currency":"NZD","conversion_rate":1,"selling_price_list":"NZ Wholesale","price_list_currency":"NZD","plc_conversion_rate":1,"ignore_pricing_rule":0,"set_warehouse":"Napier - Nm","update_stock":1,"disable_bo_check":0,"total_billing_amount":0,"total_billing_hours":0,"total_qty":30,"base_total":0,"base_net_total":0,"total_net_weight":0,"total":0,"net_total":0,"taxes_and_charges":"NZ GST 15% Wholesale - Nm","tax_category":"","other_charges_calculation":"<div class=\\"tax-break-up\\" style=\\"overflow-x: auto;\\">\\n\\t<table class=\\"table table-bordered table-hover\\">\\n\\t\\t<thead>\\n\\t\\t\\t<tr>\\n\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t<th class=\\"text-left\\">Item</th>\\n\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t<th class=\\"text-right\\">Taxable Amount</th>\\n\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t<th class=\\"text-right\\">GST @ 15.0</th>\\n\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\n\\t\\t\\t</tr>\\n\\t\\t</thead>\\n\\t\\t<tbody>\\n\\t\\t\\t\\n\\t\\t\\t\\t<tr>\\n\\t\\t\\t\\t\\t<td>Batch-test-002</td>\\n\\t\\t\\t\\t\\t<td class=\\"text-right\\">\\n\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t\\t$ 0.00\\n\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t</td>\\n\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t\\t<td class=\\"text-right\\">\\n\\t\\t\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t\\t\\t\\t(15.0%)\\n\\t\\t\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t\\t\\t\\t$ 0.00\\n\\t\\t\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\t\\t</td>\\n\\t\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t\\t\\n\\t\\t\\t\\t</tr>\\n\\t\\t\\t\\n\\t\\t</tbody>\\n\\t</table>\\n</div>","base_total_taxes_and_charges":0,"total_taxes_and_charges":0,"loyalty_points":0,"loyalty_amount":0,"redeem_loyalty_points":0,"apply_discount_on":"Grand Total","base_discount_amount":0,"additional_discount_percentage":0,"discount_amount":0,"base_grand_total":0,"base_rounding_adjustment":0,"base_rounded_total":0,"base_in_words":"","grand_total":0,"rounding_adjustment":0,"rounded_total":0,"in_words":"","total_advance":0,"outstanding_amount":0,"disable_rounded_total":1,"write_off_amount":0,"base_write_off_amount":0,"write_off_outstanding_amount_automatically":0,"allocate_advances_automatically":0,"ignore_default_payment_terms_template":0,"payment_terms_template":"Default Customer Payment Terms","base_paid_amount":0,"paid_amount":0,"base_change_amount":0,"change_amount":0,"letter_head":"NaturalMeds Statements Header","group_same_items":0,"language":"en","status":"Draft","customer_group":"Gutsi NZ","is_internal_customer":0,"is_discounted":0,"isbackorder":1,"barcode_svg":"<svg id=\\"barcode\\" height=\\"29px\\" width=\\"127px\\" x=\\"0px\\" y=\\"0px\\" viewBox=\\"0 0 127 29\\" xmlns=\\"http://www.w3.org/2000/svg\\" version=\\"1.1\\" style=\\"transform: translate(0,0)\\"><rect x=\\"0\\" y=\\"0\\" width=\\"127\\" height=\\"29\\" style=\\"fill:#ffffff;\\"></rect><g transform=\\"translate(2, 2)\\" style=\\"fill:#000000;\\"><rect x=\\"0\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect><rect x=\\"3\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"6\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"11\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"13\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"19\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect><rect x=\\"22\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"24\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"28\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect><rect x=\\"33\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"36\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect><rect x=\\"39\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"44\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"47\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"51\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect><rect x=\\"55\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"57\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"61\\" y=\\"0\\" width=\\"4\\" height=\\"25\\"></rect><rect x=\\"66\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"68\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect><rect x=\\"72\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"77\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"79\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"83\\" y=\\"0\\" width=\\"4\\" height=\\"25\\"></rect><rect x=\\"88\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect><rect x=\\"91\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"95\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"99\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"101\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"105\\" y=\\"0\\" width=\\"4\\" height=\\"25\\"></rect><rect x=\\"110\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect><rect x=\\"115\\" y=\\"0\\" width=\\"3\\" height=\\"25\\"></rect><rect x=\\"119\\" y=\\"0\\" width=\\"1\\" height=\\"25\\"></rect><rect x=\\"121\\" y=\\"0\\" width=\\"2\\" height=\\"25\\"></rect></g></svg>","debit_to":"Debtors NZ - Nm","party_account_currency":"NZD","is_opening":"No","c_form_applicable":"No","remarks":"No Remarks","amount_eligible_for_commission":0,"commission_rate":0,"total_commission":0,"against_income_account":"1143 - Gaia Herbs - Nm","exclude_invoice":0,"doctype":"Sales Invoice","items":[{"name":"a27ebb0ff8","owner":"Administrator","creation":"2023-08-31 09:41:46.530248","modified":"2023-09-20 14:00:35.297203","modified_by":"Administrator","parent":"NM-0129349","parentfield":"items","parenttype":"Sales Invoice","idx":1,"docstatus":0,"item_code":"Batch-test-002","item_name":"Batch-test-002","description":"Batch-test-002","item_group":"Products","brand":"Gaia Herbs","image":"","qty":20,"stock_uom":"Unit","uom":"Unit","conversion_factor":1,"stock_qty":20,"price_list_rate":0,"base_price_list_rate":0,"margin_type":null,"margin_rate_or_amount":0,"rate_with_margin":0,"discount_percentage":0,"discount_amount":0,"base_rate_with_margin":0,"rate":0,"amount":0,"base_rate":0,"base_amount":0,"ignore_pricing_rules":0,"pricing_rules":"[\\n \\"PRLE-0340\\"\\n]","stock_uom_rate":0,"is_free_item":0,"grant_commission":1,"net_rate":0,"net_amount":0,"base_net_rate":0,"base_net_amount":0,"delivered_by_supplier":0,"income_account":"1143 - Gaia Herbs - Nm","is_fixed_asset":0,"expense_account":"2146 - Gaia Herbs - Nm","enable_deferred_revenue":0,"weight_per_unit":0,"total_weight":0,"warehouse":"Napier - Nm","shortdated_batch":0,"incoming_rate":7.94,"allow_zero_valuation_rate":0,"item_tax_rate":"{}","actual_batch_qty":68,"actual_qty":20,"delivered_qty":0,"cost_center":"NaturalMeds - Nm","page_break":0,"doctype":"Sales Invoice Item","weight_uom":null,"discount_account":null,"has_serial_no":0,"has_batch_no":1,"min_order_qty":"","supplier":"Gaia Herbs","update_stock":0,"last_purchase_rate":0,"transaction_date":"2023-08-31","against_blanket_order":null,"bom_no":null,"manufacturer":null,"manufacturer_part_no":null,"customer_item_code":null,"valuation_rate":7.9365,"projected_qty":25,"reserved_qty":0,"has_margin":false,"child_docname":"a27ebb0ff8","validate_applied_rule":0,"price_or_product_discount":"Product","has_pricing_rule":1,"gross_profit":-158.73},{"docstatus":0,"doctype":"Sales Invoice Item","name":"new-sales-invoice-item-1","__islocal":1,"__unsaved":1,"owner":"Administrator","stock_uom":"Unit","margin_type":"","is_free_item":1,"grant_commission":0,"delivered_by_supplier":0,"is_fixed_asset":0,"enable_deferred_revenue":0,"allow_zero_valuation_rate":0,"cost_center":"NaturalMeds - Nm","page_break":0,"parent":"NM-0129349","parentfield":"items","parenttype":"Sales Invoice","idx":2,"item_code":"Batch-test-002","qty":10,"pricing_rules":"[\\"PRLE-0340\\"]","rate":0,"price_list_rate":0,"discount_percentage":100,"item_name":"Batch-test-002","description":"Batch-test-002","uom":"Unit","conversion_factor":1,"stock_qty":0,"base_price_list_rate":0,"margin_rate_or_amount":0,"rate_with_margin":0,"discount_amount":0,"base_rate_with_margin":0,"amount":0,"base_rate":0,"base_amount":0,"stock_uom_rate":0,"net_rate":0,"net_amount":0,"base_net_rate":0,"base_net_amount":0,"weight_per_unit":0,"total_weight":0,"incoming_rate":0,"actual_batch_qty":0,"actual_qty":0,"delivered_qty":0}],"backorder_items":[],"pricing_rules":[{"name":"855df1843d","creation":"2023-09-20 14:00:35.655030","modified":"2023-09-20 14:00:35.655030","modified_by":"Administrator","parent":"NM-0129349","parentfield":"pricing_rules","parenttype":"Sales Invoice","idx":1,"docstatus":0,"pricing_rule":"PRLE-0339","item_code":"Batch-test-002","child_docname":"a27ebb0ff8","rule_applied":1,"doctype":"Pricing Rule Detail"}],"packed_items":[],"timesheets":[],"taxes":[{"name":"9acb1348ed","owner":"Administrator","creation":"2023-08-31 09:41:46.530248","modified":"2023-09-20 14:00:35.297203","modified_by":"Administrator","parent":"NM-0129349","parentfield":"taxes","parenttype":"Sales Invoice","idx":1,"docstatus":0,"charge_type":"On Net Total","account_head":"9640 - GST Accrued NZ - Nm","description":"GST @ 15.0","included_in_print_rate":0,"included_in_paid_amount":0,"cost_center":"NaturalMeds - Nm","rate":15,"account_currency":"NZD","tax_amount":0,"total":0,"tax_amount_after_discount_amount":0,"base_tax_amount":0,"base_total":0,"base_tax_amount_after_discount_amount":0,"item_wise_tax_detail":"{\\"Batch-test-002\\":[15,0]}","dont_recompute_tax":0,"doctype":"Sales Taxes and Charges"}],"advances":[],"payment_schedule":[{"name":"cbff053b88","owner":"Administrator","creation":"2023-08-31 09:41:46.831787","modified":"2023-09-20 14:00:35.297203","modified_by":"Administrator","parent":"NM-0129349","parentfield":"payment_schedule","parenttype":"Sales Invoice","idx":1,"docstatus":0,"payment_term":"Default Customer Payment Terms","due_date":"2023-09-20","invoice_portion":100,"discount_type":"Percentage","discount_date":"2023-08-31","discount":0,"payment_amount":0,"outstanding":0,"paid_amount":0,"discounted_amount":0,"base_payment_amount":0,"doctype":"Payment Schedule"}],"payments":[],"sales_team":[],"_user_tags":",BO_2023-08-31","__onload":{"make_payment_via_journal_entry":0},"__last_sync_on":"2023-09-21T22:49:45.955Z","accepts_backorders":1,"__unsaved":1}'
	item_code = 'Batch-test-002'
	warehouse = 'Napier - Nm'
	qty_required = '30'
	type_required = 'Shortdated First'
	allocate_batches_table(doc, item_code, warehouse, type_required, qty_required)