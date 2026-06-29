# -*- coding: utf-8 -*-
from markupsafe import Markup
from odoo import models, fields, api, _
from odoo import Command


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    invoice_count = fields.Integer(
        string='Invoices',
        compute='_compute_invoice_count',
    )

    @api.depends('sale_id.invoice_ids')
    def _compute_invoice_count(self):
        for picking in self:
            picking.invoice_count = len(picking._get_posted_invoices())

    def _get_posted_invoices(self):
        self.ensure_one()
        return self.sale_id.invoice_ids.filtered(
            lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
        )

    def action_view_invoices(self):
        self.ensure_one()
        invoices = self._get_posted_invoices()
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Customer Invoices',
            'res_model': 'account.move',
            'context': {'default_move_type': 'out_invoice'},
        }
        if len(invoices) == 1:
            action.update({'view_mode': 'form', 'res_id': invoices.id})
        else:
            action.update({'view_mode': 'list,form', 'domain': [('id', 'in', invoices.ids)]})
        return action

    def _action_done(self):
        res = super()._action_done()
        for picking in self.filtered(lambda p: p.state == 'done' and p.return_id):
            origin = picking.return_id
            # Only proceed when the original delivery is linked to a sale order
            # AND that sale order has at least one posted (confirmed) invoice.
            if not origin.sale_id:
                continue
            posted_invoices = origin.sale_id.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
            )
            if not posted_invoices:
                continue
            picking._auto_create_credit_note()
        return res

    def _auto_create_credit_note(self):
        """Auto-create a partial draft credit note when a return delivery is validated.

        Only the returned products and their returned quantities are credited —
        a partial return produces a partial credit note, not a full reversal.
        Called only when the original delivery already has a posted invoice.
        """
        self.ensure_one()
        origin_picking = self.return_id
        invoices = origin_picking._get_posted_invoices()
        if not invoices:
            return

        today = fields.Date.context_today(self)

        # Build: product_id -> total quantity actually returned (done moves only)
        remaining_qty = {}
        for move in self.move_ids.filtered(lambda m: m.state == 'done' and m.quantity > 0):
            pid = move.product_id.id
            remaining_qty[pid] = remaining_qty.get(pid, 0.0) + move.quantity

        if not remaining_qty:
            return

        credit_notes = self.env['account.move']

        for invoice in invoices:
            # Find product lines on this invoice whose product was returned
            relevant_lines = invoice.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
                and l.product_id.id in remaining_qty
                and remaining_qty.get(l.product_id.id, 0.0) > 0
            )
            if not relevant_lines:
                continue

            # Compute how much to credit per product from this invoice,
            # consuming from remaining_qty so multiple invoices don't double-credit
            credit_qty_by_product = {}
            for line in relevant_lines:
                pid = line.product_id.id
                qty = min(remaining_qty[pid], line.quantity)
                if qty > 0:
                    credit_qty_by_product[pid] = credit_qty_by_product.get(pid, 0.0) + qty
                    remaining_qty[pid] -= qty

            if not credit_qty_by_product:
                continue

            # Create a full draft reversal, then trim lines to returned quantities
            lang = invoice.partner_id.lang or self.env.lang
            ref = self.with_context(lang=lang).env._('Return of delivery %s', self.name)
            credit_note = invoice._reverse_moves([{
                'ref': ref,
                'date': today,
                'invoice_date': today,
                'invoice_date_due': today,
                'journal_id': invoice.journal_id.id,
                'invoice_origin': self.name,
                'partner_bank_id': False,
            }], cancel=False)

            # Adjust the draft credit note to only cover returned quantities
            lines_to_delete = []
            for line in credit_note.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            ):
                pid = line.product_id.id
                if pid not in credit_qty_by_product:
                    lines_to_delete.append(line.id)
                else:
                    line.quantity = credit_qty_by_product[pid]

            if lines_to_delete:
                credit_note.write({
                    'line_ids': [Command.unlink(lid) for lid in lines_to_delete]
                })

            credit_notes |= credit_note

        if not credit_notes:
            return

        # Cross-link delivery ↔ credit note(s) via chatter.
        # Markup() is required here so the <a> tags from _get_html_link() are
        # rendered as clickable links instead of escaped plain text.
        delivery_link = self._get_html_link()
        for cn in credit_notes:
            cn.message_post(
                body=Markup('Credit note automatically created from return delivery %s') % delivery_link,
            )
        cn_links = Markup(', ').join(cn._get_html_link() for cn in credit_notes)
        self.message_post(
            body=Markup('Credit note(s) %s automatically created.') % cn_links,
        )
