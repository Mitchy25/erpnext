# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from frappe.utils import getdate, flt, add_to_date, add_days
from dateutil.relativedelta import *
from datetime import datetime, timedelta
from collections import defaultdict
import frappe
import calendar

def execute(filters=None):
	filters = frappe._dict(filters or {})
	return shipments_paid_but_not_received(filters).run()


class shipments_paid_but_not_received:
	def __init__(self, filters):
		self.filters = filters

	def run(self):
		data = self.get_data()
		columns = self.get_columns()
		return columns, data

	def get_columns(self):
		return [{
			"label": "Purchase Order",
			"fieldname": "purchase_order",
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 200
		},
                    {
			"label": "Amount Paid (Debit)",
			"fieldname": "debit_amount",
			"fieldtype": "Currency",
			"width": 200
		},
                    {
			"label": "Amount Recieved (Credit)",
			"fieldname": "credit_amount",
			"fieldtype": "Currency",
			"width": 200
		},
                    { 
			"label": "Amount Difference",
			"fieldname": "credit_difference",
			"fieldtype": "Currency",
			"width": 200
		}]


	def get_data(self):
		params = {}
		where_date = """"""
		where = """"""

		if "from_date" in self.filters.keys():
			where_date += "AND gl.posting_date BETWEEN %(from_date)s "
			params["from_date"] = self.filters["from_date"]
		if "to_date" in self.filters.keys():
			where_date += "AND %(to_date)s "
			params["to_date"] = self.filters["to_date"]
		if "supplier" in self.filters.keys():
			where += "AND gl.AGAINST = %(supplier)s "
			params["supplier"] = self.filters["supplier"]
		if "purchase_order" in self.filters.keys():
			where += "AND p.purchase_order = %(purchase_order)s "
			params["purchase_order"] = self.filters["purchase_order"] 

		debit = """
		SELECT  p.purchase_order, gl.voucher_no,  gl.debit
		FROM `tabGL Entry` gl
		INNER JOIN `tabPurchase Invoice Item` p
		ON gl.voucher_no = p.parent
		WHERE gl.account = "Stock Received But Not Billed - Nm" 
		AND p.expense_account = "Stock Received But Not Billed - Nm"
		AND gl.debit != 0.0
		{where}
		{where_date}
		GROUP BY p.purchase_order
		ORDER BY gl.posting_date ,  p.purchase_order
		""".format(where=where, where_date=where_date)
		debit = frappe.db.sql(debit, params, as_dict=True)


		credit = """
		SELECT p.purchase_order, gl.voucher_no, gl.credit
		FROM `tabGL Entry` gl
		INNER JOIN `tabPurchase Receipt Item` p ON gl.voucher_no = p.parent
		WHERE gl.account = "Stock Received But Not Billed - Nm" 
		AND gl.debit = 0.0
		{where}
		{where_date}
		GROUP BY p.purchase_order
		ORDER BY gl.posting_date ,  p.purchase_order
		""".format(where=where, where_date=where_date)
		credit = frappe.db.sql(credit, params, as_dict=True)

		running_totals = {}

		for debit_entry in debit:
			purchase_order = debit_entry['purchase_order']
			debit_amount = debit_entry['debit']
			if purchase_order != None:
				if purchase_order in running_totals:
					running_totals[purchase_order]['debit'] += debit_amount
				else:
					running_totals[purchase_order] = {'debit': debit_amount, 'credit': 0}

		for credit_entry in credit:
			purchase_order = credit_entry['purchase_order']
			credit_amount = credit_entry['credit']
			if purchase_order != None:
				if purchase_order in running_totals:
					running_totals[purchase_order]['credit'] += credit_amount
				else:
					running_totals[purchase_order] = {'debit': 0, 'credit': credit_amount}


		chart_data = [{'purchase_order': key, 'debit_amount': value['debit'], 'credit_amount': value['credit'], 'credit_difference': round(value['credit'] - value['debit'], 2)} for key, value in running_totals.items()]

		return sorted(chart_data, key=lambda x: x["credit_difference"], reverse=True)