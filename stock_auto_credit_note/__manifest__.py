# -*- coding: utf-8 -*-
{
    'name': 'Auto Credit Note from Return Orders',
    'version': '19.0.1.0.0',
    'category': 'Invoicing',
    'summary': 'Automatically create a draft credit note when a return delivery is validated and an invoice exists',
    'description': """
Auto Credit Note from Return Delivery
======================================
When a return order is validated, this module automatically creates a draft
credit note (out_refund) for every posted customer invoice linked to the
original delivery's sale order. No manual steps required.

Flow:
  1. Customer delivery validated → invoice posted.
  2. User creates a return of that delivery.
  3. Return delivery validated → credit note created automatically in draft.
  4. Accountant reviews and posts the credit note.

Features:
- Fully automatic — no wizard, no button click.
- Credit note created in draft for accountant review before posting.
- Chatter messages on both the return delivery and the credit note link them.
- Invoice smart button on the original delivery shows linked invoices.
    """,
    'author': 'Dvija Technologies',
    'depends': ['stock', 'account', 'sale_stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
