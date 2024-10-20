// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sales Partner Transaction Summary"] = {
	filters: [
		{
			fieldname: "sales_partner",
			label: __("Sales Partner"),
			fieldtype: "Link",
			options: "Sales Partner",
		},
		{
			fieldname: "doctype",
			label: __("Document Type"),
			fieldtype: "Select",
			options: "Sales Order\nDelivery Note\nSales Invoice",
			default: "Sales Invoice"
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options: "Brand",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Link",
			options: "Territory",
		},
		{
			fieldname:"group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options:["Default (Document type)", "Customer Name"],
			default: "Default (Document type)",
			reqd: 1
		},
		{
			fieldname:"currency",
			label: __("Currency"),
			fieldtype: "Select",
			options:["", "NZD", "AUD"],
			default: ""
		},
		{
			fieldname:"show_return_entries",
			label: __("Show Return Entries"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname:"get_products",
			label: __("Get Products"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname:"get_tests",
			label: __("Get Tests and Test Kits"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
