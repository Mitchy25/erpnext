# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe, erpnext
from frappe import _, msgprint
from frappe.utils import get_url

def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns(filters)
	data = get_entries(filters)

	return columns, data


def get_columns(filters):
	if not filters.get("doctype"):
		msgprint(_("Please select the document type first"), raise_exception=1)

	columns = [
		# {
		# 	"label": _("Customer"),
		# 	"options": "Customer",
		# 	"fieldname": "customer",
		# 	"fieldtype": "Link",
		# 	"width": 100
		# },
		{
			"label": _("Sales Partner Code"),
			"options": "Customer",
			"fieldname": "sales_partner_code",
			"fieldtype": "Link",
			"width": 100
		},
		{
			"label": _("Sales Partner"),
			"options": "Sales Partner",
			"fieldname": "sales_partner",
			"fieldtype": "Link",
			"width": 100
		},
				{
			"label": _("Sales Partner Email"),
			"fieldname": "customer_primary_email_address",
			"fieldtype": "DATA",
			"width": 200
		},
				{
			"label": _("Branch Code"),
			"fieldname": "branch_code",
			"fieldtype": "data",
			"width": 100
		},
		{
			"label": _("Account Number"),
			"fieldname": "account_number",
			"fieldtype": "data",
			"width": 100
		},
		{
			"label": _("Sales Partner Rebate preference"),
			"fieldname": "bank_details",
			"fieldtype": "Data",
			"width": 200
		},
		{
			"label": _(filters["doctype"]),
			"options": filters["doctype"],
			"fieldname": "name",
			"fieldtype": "Link",
			"width": 140,
		},
		{
			"label": _("Customer Name"),
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 140
		},
		# {
		# 	"label": _("Territory"),
		# 	"options": "Territory",
		# 	"fieldname": "territory",
		# 	"fieldtype": "Link",
		# 	"width": 100
		# },
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 100
		},
		# {
		# 	"label": _("Item Code"),
		# 	"fieldname": "item_code",
		# 	"fieldtype": "Link",
		# 	"options": "Item",
		# 	"width": 120
		# },
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 140
		},
		# {
		# 	"label": _("Item Group"),
		# 	"fieldname": "item_group",
		# 	"fieldtype": "Link",
		# 	"options": "Item Group",
		# 	"width": 100
		# },
		# {
		# 	"label": _("Brand"),
		# 	"fieldname": "brand",
		# 	"fieldtype": "Link",
		# 	"options": "Brand",
		# 	"width": 100
		# },
		{
			"label": _("Quantity"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 80
		},
		# {
		# 	"label": _("Rate"),
		# 	"fieldname": "rate",
		# 	"fieldtype": "Currency",
		# 	"width": 80
		# },
		{
			"label": _("Amount"),
			"fieldname": "amount",
			"fieldtype": "Currency",
			"width": 120
		},

		# {
		# 	"label": _("Commission Rate %"),
		# 	"fieldname": "commission_rate",
		# 	"fieldtype": "Data",
		# 	"width": 80
		# },
		# {
		# 	"label": _("Commission"),
		# 	"fieldname": "commission",
		# 	"fieldtype": "Currency",
		# 	"width": 120
		# },
		{
			"label": _('Rebate (SalePrice - WS)'),
			"fieldname": "commission_wholesale",
			"fieldtype": "Currency",
			"width": 120
		}
		
	]

	if erpnext.get_default_company() != "RN Labs":
		columns.append({
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"width": 120
		})

	return columns


def get_entries(filters):
	date_field = "transaction_date" if filters.get("doctype") in ["Sales Order", "Sales Invoice"] else "posting_date"

	conditions = get_conditions(filters, date_field)
	entries = frappe.db.sql(
		"""
		SELECT
			s.customer as sales_partner_code,
			dt.name, 
			if(s.preference = "Refund to Account", a.branch_code, 'N/A') as branch_code,
			if(s.preference = "Refund to Account", a.bank_account_no, 'N/A') as account_number,
			dt.customer, dt.territory, dt.{date_field} as posting_date, dt.currency, 
			s.preference as bank_details, dt.selling_price_list as price_list,
			dt_item.item_code, dt_item.item_name, dt.customer_name,
			SUM(dt_item.net_rate) as rate, SUM(dt_item.qty) as qty, SUM(dt_item.net_amount) as amount,
			ROUND(((dt_item.net_rate * dt.commission_rate) / 100), 2) as commission,
			dt_item.brand, dt.sales_partner,dts.customer_primary_email_address, dt.commission_rate, dt_item.item_group, dt_item.item_code, dt_item.uom
		FROM
			`tab{doctype}` dt
		join `tab{doctype} Item` dt_item on dt_item.parent = dt.name
		join `tabSales Partner` s on s.name = dt.sales_partner
		LEFT join `tabCustomer` dts on dts.name = s.customer
		LEFT join `tabBank Account` a on s.bank_account = a.name
		
		WHERE
			{cond} and dt.name = dt_item.parent 
			and dt.docstatus = 1
			and dt_item.item_code NOT IN ("HAND-FEE", "SHIP1", "SHIP2", "SHIP3", "CREDIT ADJ")
			and dt.sales_partner is not null 
			and dt.sales_partner != ''
		GROUP BY dt.name, dt_item.item_code
		order by dt.name desc, dt.sales_partner
		
		""".format(
			date_field=date_field, doctype=filters.get("doctype"), cond=conditions
		),
		filters,
		as_dict=1
	)
	if filters["doctype"] == "Sales Invoice":
		entries = calculate_ws_commission(entries, filters)
	return entries


def get_conditions(filters, date_field):
	conditions = "1=1"

	for field in ["company", "customer", "territory", "sales_partner"]:
		if filters.get(field):
			conditions += " and dt.{0} = %({1})s".format(field, field)

	if filters.get("from_date"):
		conditions += " and dt.{0} >= %(from_date)s".format(date_field)

	if filters.get("to_date"):
		conditions += " and dt.{0} <= %(to_date)s".format(date_field)

	if not filters.get("show_return_entries"):
		conditions += " and dt_item.qty > 0.0"
	
	if filters.get("get_products") or filters.get("get_tests"):
		in_group = ['"Test Kits"','"Tests"'] if filters.get("get_tests") == 1 else []
		if filters.get("get_products") == 1:
			in_group.append("'Products'")
		conditions += f" and dt_item.item_group in ({','.join(in_group)})"
	# frappe.msgprint(conditions)

	if filters.get("brand"):
		conditions += " and dt_item.brand = %(brand)s"

	if filters.get("item_group"):
		lft, rgt = frappe.get_cached_value("Item Group", filters.get("item_group"), ["lft", "rgt"])

		conditions += """ and dt_item.item_group in (select name from
			`tabItem Group` where lft >= %s and rgt <= %s)""" % (
			lft,
			rgt,
		)
	
	return conditions




def calculate_ws_commission(entries, filters):
	from frappe.utils import flt
	item_prices = frappe.db.get_all("Item Price", 
	filters=[["selling", "=", "1"]],
	or_filters=[
    ["valid_upto", ">=", filters.get("from_date")],
    ["valid_upto", "is", "not set"]
	],
	fields=["item_code", "price_list", "valid_from", "valid_upto", "price_list_rate"],
	order_by="valid_from")
	item_dict = {}
	for item in item_prices:
		if item["item_code"] not in item_dict:
			item_dict[item["item_code"]] = {}
		current_item_dict = item_dict[item["item_code"]]
		if item["price_list"] not in current_item_dict:
			current_item_dict[item["price_list"]] = []
		current_item_dict[item["price_list"]].append(item)

	for entry in entries:
		current_price = None
		entry_price_list = entry["price_list"]
		entry_price_list = entry_price_list.split()[0]
		entry_price_list += " Wholesale"

		entry['wholesale_price'], entry['wholesale_amount'] = get_wholesale_price(entry)
		if entry['wholesale_price']:
			entry["commission_wholesale"] = flt(entry["amount"] - (entry['wholesale_price']*entry["qty"]), 2)
			if entry["commission_wholesale"] < 0:
				entry["commission_wholesale"] = 0
		else:

			msgprint("No wholesale price for <a href='" + get_url() + "/app/item/" + entry["item_code"] + "' target='_blank'>" + entry["item_code"] + "</a>. Please set a wholesale price and then re-run report")
			return []
		
	return entries

def get_wholesale_price(entry):
	get_price_list_rate_args = {
		"customer": entry.customer,
		"item_code": entry.item_code,
		"transaction_date": entry.posting_date,
		"posting_date": entry.posting_date,
		"uom": entry.uom
	}
	price_list = entry.price_list.split(" ")[0] + " Wholesale"
	get_price_list_rate_args['price_list'] = price_list
	price_list_rate = get_price_list_rate_for(get_price_list_rate_args, entry.item_code)
	return price_list_rate, price_list_rate*entry.qty