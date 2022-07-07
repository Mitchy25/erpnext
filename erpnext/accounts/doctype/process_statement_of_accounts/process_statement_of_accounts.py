# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import copy

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, nowdate, add_months, format_date, getdate, today
from frappe.utils.jinja import validate_template
from frappe.utils.pdf import get_pdf
from frappe.www.printview import get_print_style

from erpnext import get_company_currency
from erpnext.accounts.party import get_party_account_currency
from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	execute as get_ageing,
)
from erpnext.accounts.report.general_ledger.general_ledger import execute as get_soa

from fxnmrnth.fxnmrnth.doctype.statement_of_account.statement_of_account import create_statement
import pdb

class ProcessStatementOfAccounts(Document):
	def validate(self):
		if not self.subject:
			self.subject = "Statement Of Accounts for {{ customer.name }}"
		if not self.body:
			self.body = "Hello {{ customer.name }},<br>PFA your Statement Of Accounts from {{ doc.from_date }} to {{ doc.to_date }}."

		validate_template(self.subject)
		validate_template(self.body)

		if not self.customers:
			frappe.throw(_("Customers not selected."))

		if self.enable_auto_email:
			self.to_date = self.start_date
			self.from_date = add_months(self.to_date, -1 * self.filter_duration)


def get_report_pdf(doc, consolidated=True, customer=None):
	statement_dict = {}
	ageing = ""
	base_template_path = "frappe/www/printview.html"
	template_path = (
		"erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts.html"
	)
	
	for entry in doc.customers:
		if customer:
			if entry.customer != customer:
				continue

		if doc.include_ageing:
			ageing_filters = frappe._dict({
				'company': doc.company,
				'report_date': doc.to_date,
				'ageing_based_on': doc.ageing_based_on,
				'range1': 30,
				'range2': 60,
				'range3': 90,
				'range4': 90,	#Ignored but required
				'customer': entry.customer,
				'show_not_yet_due': 1
			})
			col1, ageing = get_ageing(ageing_filters)

			if ageing:
				ageing[0]["ageing_based_on"] = doc.ageing_based_on

		tax_id = frappe.get_doc('Customer', entry.customer).tax_id
		customer_name = frappe.get_doc('Customer', entry.customer).customer_name
		presentation_currency = get_party_account_currency('Customer', entry.customer, doc.company) \
				or doc.currency or get_company_currency(doc.company)
		if doc.letter_head:
			from frappe.www.printview import get_letter_head

			letter_head = get_letter_head(doc, 0)

		filters= frappe._dict({
			'from_date': doc.from_date,
			'to_date': doc.to_date,
			'company': doc.company,
			'finance_book': doc.finance_book if doc.finance_book else None,
			'account': [doc.account] if doc.account else None,
			'party_type': 'Customer',
			'party': [entry.customer],
			'party_name': [customer_name],
			'presentation_currency': presentation_currency,
			'group_by': doc.group_by,
			'currency': doc.currency,
			'cost_center': [cc.cost_center_name for cc in doc.cost_center],
			'project': [p.project_name for p in doc.project],
			'show_opening_entries': 1,
			'include_default_book_entries': 0,
			'tax_id': tax_id if tax_id else None
		})
		col, res = get_soa(filters)

		for x in [0, -2, -1]:
			res[x]["account"] = res[x]["account"].replace("'", "")

		if len(res) == 3:
			#No Transactions this month
			if res[2]["debit"] == 0:
				#No outstanding balance
				continue
			else:
				res.insert(2,{
					"account":"No transactions during the period",
					"debit":"",
					"credit":"",
					"debit_in_account_currency":"",
					"credit_in_account_currency":"",
					"balance":0,
					"account_currency": res[1]["account_currency"]
				})

		if res[-1]["balance"] == 0:
			#No outstanding balance
			continue
		
		if doc.exclude_balances_below:
			if res[-1]["balance"] < float(doc.exclude_balances_below):
				continue

		html = frappe.render_template(
			template_path,
			{
				"filters": filters,
				"data": res,
				"ageing": ageing[0] if (doc.include_ageing and ageing) else None,
				"letter_head": letter_head if doc.letter_head else None,
				"terms_and_conditions": frappe.db.get_value(
					"Terms and Conditions", doc.terms_and_conditions, "terms"
				)
				if doc.terms_and_conditions
				else None,
			},
		)

		html = frappe.render_template(
			base_template_path,
			{"body": html, "css": get_print_style(), "title": "Statement For " + entry.customer},
		)
		statement_dict[entry.customer] = html

	if not bool(statement_dict):
		return False
	elif consolidated:
		result = "".join(list(statement_dict.values()))
		return get_pdf(result, {"orientation": doc.orientation})
	else:
		for customer, statement_html in statement_dict.items():
			statement_dict[customer] = get_pdf(statement_html, {"orientation": doc.orientation})
		return statement_dict

def get_customers_based_on_territory_or_customer_group(customer_collection, collection_name):
	fields_dict = {
		"Customer Group": "customer_group",
		"Territory": "territory",
	}
	collection = frappe.get_doc(customer_collection, collection_name)
	selected = [
		customer.name
		for customer in frappe.get_list(
			customer_collection,
			filters=[["lft", ">=", collection.lft], ["rgt", "<=", collection.rgt]],
			fields=["name"],
			order_by="lft asc, rgt desc",
		)
	]
	return frappe.get_list(
		"Customer",
		fields=["name", "email_id"],
		filters=[[fields_dict[customer_collection], "IN", selected]],
	)

def get_logic_context(doc):
	return {"doc": doc, "nowdate": nowdate, "frappe": frappe._dict(utils=frappe.utils)}

def get_customers_based_on_custom_logic(custom_logic):
	'''Get list of customers'''
	customerList = frappe.db.sql("""
		SELECT
			name,
			customer_statement_email_address as email_id
		FROM 
			`tabCustomer`
		WHERE
			disabled = 0""",
		as_dict=1,
	)

	passCustomerList = []

	for customer in customerList:
		doc = frappe.get_doc("Customer", customer.name)
		skipped = 0

		if custom_logic:
			or_condition = " or \\\n"
			if or_condition in custom_logic:
				conditions = custom_logic.split(or_condition)
				for condition in conditions:
					condition = condition.strip()
					if frappe.safe_eval(condition, None, get_logic_context(doc)):
						skipped = 1
						break
				if skipped:
					continue
			else:
				if frappe.safe_eval(custom_logic.strip(), None, get_logic_context(doc)):
					skipped = 1
					continue
			
		if skipped == 0:
			passCustomerList.append(customer)

	return passCustomerList

def get_customers_based_on_sales_person(sales_person):
	lft, rgt = frappe.db.get_value("Sales Person", sales_person, ["lft", "rgt"])
	records = frappe.db.sql(
		"""
		select distinct parent, parenttype
		from `tabSales Team` steam
		where parenttype = 'Customer'
			and exists(select name from `tabSales Person` where lft >= %s and rgt <= %s and name = steam.sales_person)
	""",
		(lft, rgt),
		as_dict=1,
	)
	sales_person_records = frappe._dict()
	for d in records:
		sales_person_records.setdefault(d.parenttype, set()).add(d.parent)
	if sales_person_records.get("Customer"):
		return frappe.get_list(
			"Customer",
			fields=["name", "email_id"],
			filters=[["name", "in", list(sales_person_records["Customer"])]],
		)
	else:
		return []

def get_recipients_and_cc(customer, doc):
	recipients = []
	for clist in doc.customers:
		if clist.customer == customer:
			recipients.append(clist.billing_email)
			if doc.primary_mandatory and clist.primary_email:
				recipients.append(clist.primary_email)
	cc = []
	if doc.cc_to != "":
		try:
			cc = [frappe.get_value("User", doc.cc_to, "email")]
		except Exception:
			pass

	return recipients, cc

def get_context(customer, doc):
	template_doc = copy.deepcopy(doc)
	del template_doc.customers
	template_doc.from_date = format_date(template_doc.from_date)
	template_doc.to_date = format_date(template_doc.to_date)
	return {
		"doc": template_doc,
		"customer": frappe.get_doc("Customer", customer),
		"frappe": frappe.utils,
	}

@frappe.whitelist()
def fetch_customers(customer_collection, collection_name, primary_mandatory, custom_logic):
	customer_list = []
	customers = []

	if customer_collection == "Sales Person":
		customers = get_customers_based_on_sales_person(collection_name)
		if not bool(customers):
			frappe.throw(_("No Customers found with selected options."))
	elif customer_collection == "Custom Logic":
		customers = get_customers_based_on_custom_logic(custom_logic)
		if not bool(customers):
			frappe.throw(_("No Customers found with selected options."))
	else:
		if customer_collection == "Sales Partner":
			customers = frappe.get_list(
				"Customer",
				fields=["name", "email_id"],
				filters=[["default_sales_partner", "=", collection_name]],
			)
		else:
			customers = get_customers_based_on_territory_or_customer_group(
				customer_collection, collection_name
			)

	for customer in customers:
		primary_email = customer.get("email_id") or ""
		billing_email = get_customer_emails(customer.name, 1, billing_and_primary=False)

		if int(primary_mandatory):
			if primary_email == "":
				continue
		elif (billing_email == "") and (primary_email == ""):
			continue

		customer_list.append(
			{"name": customer.name, "primary_email": primary_email, "billing_email": billing_email}
		)
	return customer_list

@frappe.whitelist()
def get_customer_emails(customer_name, primary_mandatory, billing_and_primary=True):
	"""Returns first email from Contact Email table as a Billing email
	when Is Billing Contact checked
	and Primary email- email with Is Primary checked"""

	# billing_email = frappe.db.sql(
	# 	"""
	# 	SELECT
	# 		email.email_id
	# 	FROM
	# 		`tabContact Email` AS email
	# 	JOIN
	# 		`tabDynamic Link` AS link
	# 	ON
	# 		email.parent=link.parent
	# 	JOIN
	# 		`tabContact` AS contact
	# 	ON
	# 		contact.name=link.parent
	# 	WHERE
	# 		link.link_doctype='Customer'
	# 		and link.link_name=%s
	# 		and contact.is_billing_contact=1
	# 	ORDER BY
	# 		contact.creation desc""",
	# 	customer_name,
	# )

	"""Returns customer statement email address"""
	billing_email = frappe.db.sql(
		"""
		SELECT
			customer_statement_email_address
		FROM
			`tabCustomer`
		WHERE
			name=%s""",
		customer_name,
	)

	if len(billing_email) == 0 or (billing_email[0][0] is None):
		if billing_and_primary:
			frappe.throw(_("No billing email found for customer: {0}").format(customer_name))
		else:
			return ""

	if billing_and_primary:
		# primary_email = frappe.get_value("Customer", customer_name, "email_id")
		primary_email = frappe.get_value("Customer", customer_name, "customer_statement_email_address")
		if primary_email is None and int(primary_mandatory):
			frappe.throw(_("No primary email found for customer: {0}").format(customer_name))
		return [primary_email or "", billing_email[0][0]]
	else:
		return billing_email[0][0] or ""

@frappe.whitelist()
def download_statements(document_name):
	doc = frappe.get_doc("Process Statement Of Accounts", document_name)
	report = get_report_pdf(doc)
	if report:
		frappe.local.response.filename = doc.company + " - Statement of Account.pdf"
		frappe.local.response.filecontent = report
		frappe.local.response.type = "download"

@frappe.whitelist()
def download_individual_statement(document_name,customer):
	doc = frappe.get_doc("Process Statement Of Accounts", document_name)
	report = get_report_pdf(doc,consolidated=True,customer=customer)
	if report:
		frappe.local.response.filename = doc.company + " - Statement of Account - " + customer + ".pdf"
		frappe.local.response.filecontent = report
		frappe.local.response.type = "download"

@frappe.whitelist()
def send_emails(document_name, from_scheduler=False):
	doc = frappe.get_doc("Process Statement Of Accounts", document_name)
	report = get_report_pdf(doc, consolidated=False)

	if report:
		for customer, report_pdf in report.items():
			attachments = [{"fname": doc.company + " - Statement of Account - " + customer + ".pdf", "fcontent": report_pdf}]

			recipients, cc = get_recipients_and_cc(customer, doc)
			context = get_context(customer, doc)
			subject = frappe.render_template(doc.subject, context)
			message = frappe.render_template(doc.body, context)


			frappe.enqueue(
				queue="short",
				method=frappe.sendmail,
				recipients=recipients,
				# sender=frappe.session.user, #Send as default outgoing
				cc=cc,
				subject=subject,
				message=message,
				# now=True,
				is_async=True,
				reference_doctype="Process Statement Of Accounts",
				reference_name=document_name,
				attachments=attachments,
			)

			doc = frappe.get_doc('Customer', customer)
			doc.add_comment('Customer has been sent a Statement of Accounts Email from us.')

			#Create Statement Doc
			create_statement(doc, customer, recipients[0])

		if doc.enable_auto_email and from_scheduler:
			new_to_date = getdate(today())
			if doc.frequency == "Weekly":
				new_to_date = add_days(new_to_date, 7)
			else:
				new_to_date = add_months(new_to_date, 1 if doc.frequency == "Monthly" else 3)
			new_from_date = add_months(new_to_date, -1 * doc.filter_duration)
			doc.add_comment(
				"Comment", "Emails sent on: " + frappe.utils.format_datetime(frappe.utils.now())
			)
			doc.db_set("to_date", new_to_date, commit=True)
			doc.db_set("from_date", new_from_date, commit=True)
		return True
	else:
		return False

@frappe.whitelist()
def send_auto_email():
	
	selected = frappe.get_list(
		"Process Statement Of Accounts",
		filters={"to_date": today(), "enable_auto_email": 1},
	)
	for entry in selected:
		customerAccountDoc = frappe.get_doc("Process Statement Of Accounts", entry)

		if customerAccountDoc.collection_name or (customerAccountDoc.customer_collection == "Custom Logic" and customerAccountDoc.logic):
			#Refresh customers in 'Customers' table
			if customerAccountDoc.customer_collection == "Custom Logic":
				custom_logic = customerAccountDoc.logic
			else:
				custom_logic = None
			
			customerAccountDoc.set('customers', [])
			customerList = fetch_customers(customerAccountDoc.customer_collection, customerAccountDoc.collection_name, customerAccountDoc.primary_mandatory, custom_logic)
			for customer in customerList:
				customerAccountDoc.append('customers', {
					"customer": customer['name'],
					"primary_email": customer['primary_email'],
					"billing_email": customer['billing_email']
				})
			customerAccountDoc.save()

		send_emails(entry.name, from_scheduler=True)
	return True
