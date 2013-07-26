# -*- encoding: utf-8 -*-
#################################################################################
#                                                                               #
# Copyright (C) 2009  Renato Lima - Akretion                                    #
# Copyright (C) 2012  Raphaël Valyi - Akretion                                  #
#                                                                               #
#This program is free software: you can redistribute it and/or modify           #
#it under the terms of the GNU Affero General Public License as published by    #
#the Free Software Foundation, either version 3 of the License, or              #
#(at your option) any later version.                                            #
#                                                                               #
#This program is distributed in the hope that it will be useful,                #
#but WITHOUT ANY WARRANTY; without even the implied warranty of                 #
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                  #
#GNU Affero General Public License for more details.                            #
#                                                                               #
#You should have received a copy of the GNU Affero General Public License       #
#along with this program.  If not, see <http://www.gnu.org/licenses/>.          #
#################################################################################

import decimal_precision as dp
from osv import fields, osv
from tools.translate import _


class sale_shop(osv.osv):
    _inherit = 'sale.shop'

    _columns = {
                'default_fo_category_id': fields.many2one('l10n_br_account.fiscal.operation.category', 'Categoria Fiscal Padrão'),
    }

sale_shop()


class sale_order(osv.osv):
    _inherit = 'sale.order'

    def _get_order(self, cr, uid, ids, context={}):
        result = super(sale_order, self)._get_order(cr, uid, ids, context)
        return result.keys()

    def _invoiced_rate(self, cursor, user, ids, name, arg, context=None):
        res = {}
        for sale in self.browse(cursor, user, ids, context=context):
            if sale.invoiced:
                res[sale.id] = 100.0
                continue
            tot = 0.0
            for invoice in sale.invoice_ids:
                if invoice.state not in ('draft', 'cancel') and invoice.fiscal_operation_id.id == sale.fiscal_operation_id.id:
                    tot += invoice.amount_untaxed
            if tot:
                res[sale.id] = min(100.0, tot * 100.0 / (sale.amount_untaxed or 1.00))
            else:
                res[sale.id] = 0.0
        return res

    def _get_weight(self, cr, uid, ids, name, arg, context=None):
        res = {}
        for order in self.browse(cr, uid, ids, context=context):
            weight = 0.0
            for line in order.order_line:
                weight += line.th_weight * line.product_uom_qty
            res[order.id] = weight

        return res

    _columns = {
        'order_line': fields.one2many(
            'sale.order.line', 'order_id', 'Order Lines', readonly=False,
            states={
                'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]
                }
            ),
        'fiscal_operation_category_id': fields.many2one(
            'l10n_br_account.fiscal.operation.category', 'Categoria',
            domain="[('type','=','output'),('use_sale','=',True)]",
            readonly=False,
            states={
                'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]
                }
            ),
        'fiscal_operation_id': fields.many2one(
            'l10n_br_account.fiscal.operation', u'Operação Fiscal',
            readonly=False,
            states={
                'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]
                },
            domain="[('fiscal_operation_category_id','=',fiscal_operation_category_id),('type','=','output'),('use_sale','=',True)]"
            ),
        'fiscal_position': fields.many2one(
            'account.fiscal.position', 'Fiscal Position', readonly=False,
            states={
                'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]
                }
            ),
        'invoiced_rate': fields.function(
            _invoiced_rate, method=True, string='Invoiced', type='float'
            ),
        'freight': fields.float('Valor do Frete', digits_compute=dp.get_precision('Product Price'), help="Valor do Frete"),
        'weight': fields.function(_get_weight, string='Peso Estimado', type='char')
       }

    def button_dummy(self, cr, uid, ids, context=None):
        res = {}
        res = self._get_weight(cr, uid, ids, None, None, context)
        return res

    def _amount_line_tax(self, cr, uid, line, context=None):
        val = 0.0
        freight = 0.0
        freight_rate = 0.0
        order_lines = self.pool.get('sale.order.line').search(cr, uid, [('order_id', '=', line.order_id.id)], context=context)

        if line.order_id.amount_untaxed:
            freight_rate = (line.order_id.freight / line.order_id.amount_untaxed) * line.price_subtotal
        for c_tax in self.pool.get('account.tax').compute_all(cr, uid, line.tax_id, line.price_unit * (1 - (line.discount or 0.0) / 100.0), line.product_uom_qty, line.order_id.partner_invoice_id.id, line.product_id, line.order_id.partner_id, freight_rate, fiscal_operation=line.fiscal_operation_id)['taxes']:
            tax_brw = self.pool.get('account.tax').browse(cr, uid, c_tax['id'])
            if tax_brw.tax_add:
                val += c_tax.get('amount', 0.0)
        return val

    def onchange_partner_id(self, cr, uid, ids, partner_id=False,
                            shop_id=False, fiscal_operation_category_id=False,
                            context=None):

        result = super(sale_order, self).onchange_partner_id(cr, uid, ids, partner_id)

        if not shop_id or not partner_id:
            return result

        obj_shop = self.pool.get('sale.shop').browse(cr, uid, shop_id)
        company_id = obj_shop.company_id.id

        if not fiscal_operation_category_id:
            fiscal_operation_category_id = obj_shop.default_fo_category_id.id
            result['fiscal_operation_category_id'] = fiscal_operation_category_id

        obj_fiscal_position_rule = self.pool.get('account.fiscal.position.rule')
        fiscal_result = obj_fiscal_position_rule.fiscal_position_map(
            cr, uid, partner_id, company_id, fiscal_operation_category_id,
            context={'use_domain': ('use_sale', '=', True)}
            )

        result['value'].update(fiscal_result)

        return result

    def onchange_shop_id(self, cr, uid, ids, shop_id=False, partner_id=False,
                         fiscal_operation_category_id=False):

        result = super(sale_order, self).onchange_shop_id(cr, uid, ids, shop_id, partner_id)

        if not shop_id:
            return result

        obj_shop = self.pool.get('sale.shop').browse(cr, uid, shop_id)
        company_id = obj_shop.company_id.id

        result['value']['fiscal_operation_category_id'] = fiscal_operation_category_id or (obj_shop.default_fo_category_id and obj_shop.default_fo_category_id.id or False)

        if not partner_id:
            return result

        obj_fiscal_position_rule = self.pool.get('account.fiscal.position.rule')
        fiscal_result = obj_fiscal_position_rule.fiscal_position_map(
            cr, uid, partner_id, company_id, fiscal_operation_category_id,
            context={'use_domain': ('use_sale', '=', True)}
            )

        result['value'].update(fiscal_result)

        return result

    def onchange_fiscal_operation_category_id(self, cr, uid, ids, partner_id, 
                                              shop_id=False, fiscal_operation_category_id=False):

        result = {'value': {'fiscal_operation_id': False, 'fiscal_position': False}}

        if not shop_id or not partner_id or not fiscal_operation_category_id:
            return result

        obj_shop = self.pool.get('sale.shop').browse(cr, uid, shop_id)
        company_id = obj_shop.company_id.id

        result['value']['fiscal_operation_category_id'] = fiscal_operation_category_id or (obj_shop.default_fo_category_id and obj_shop.default_fo_category_id.id)

        obj_fiscal_position_rule = self.pool.get('account.fiscal.position.rule')

        fiscal_result = obj_fiscal_position_rule.fiscal_position_map(
            cr, uid, partner_id, company_id,
            fiscal_operation_category_id,
            context={'use_domain': ('use_sale', '=', True)}
            )

        result['value'].update(fiscal_result)
        del result['value']['fiscal_operation_category_id']

        return result


    def _prepare_invoice(self, cr, uid, order, lines, context=None):
        """Prepare the dict of values to create the new invoice for a
           sales order. This method may be overridden to implement custom
           invoice generation (making sure to call super() to establish
           a clean extension chain).

           :param browse_record order: sale.order record to invoice
           :param list(int) line: list of invoice line IDs that must be
                                  attached to the invoice
           :return: dict of value to create() the invoice
        """
        if context is None:
            context = {}
        journal_ids = self.pool.get('account.journal').search(cr, uid,
            [('type', '=', 'sale'), ('company_id', '=', order.company_id.id)],
            limit=1)
        if not journal_ids:
            raise osv.except_osv(_('Error!'),
                _('Please define sales journal for this company: "%s" (id:%d).') % (order.company_id.name, order.company_id.id))
        invoice_vals = {
            'name': order.client_order_ref or '',
            'origin': order.name,
            'type': 'out_invoice',
            'reference': order.client_order_ref or order.name,
            'account_id': order.partner_id.property_account_receivable.id,
            'partner_id': order.partner_invoice_id.id,
            'journal_id': journal_ids[0],
            'invoice_line': [(6, 0, lines)],
            'currency_id': order.pricelist_id.currency_id.id,
            'comment': order.note,
            'payment_term': order.payment_term and order.payment_term.id or False,
            'fiscal_position': order.fiscal_position.id or order.partner_id.property_account_position.id,
            'date_invoice': context.get('date_invoice', False),
            'company_id': order.company_id.id,
            'amount_freight': order.freight,
            'user_id': order.user_id and order.user_id.id or False
        }

        # Care for deprecated _inv_get() hook - FIXME: to be removed after 6.1
        invoice_vals.update(self._inv_get(cr, uid, order, context=context))
        return invoice_vals

    def _make_invoice(self, cr, uid, order, lines, context=None):
        inv_obj = self.pool.get('account.invoice')
        obj_invoice_line = self.pool.get('account.invoice.line')
        lines_service = []
        lines_product = []
        inv_ids = []
        inv_id_product = False
        inv_id_service = False
        amount_freight = 0.0

        if context is None:
            context = {}

        obj_company = self.pool.get('res.company').browse(cr, uid, order.company_id.id)
        '''
        FIXME: check if fiscal_operation_category_id.fiscal_type is service or
        product and change list below.
        '''
        fiscal_document_serie_ids = [fdoc for fdoc in obj_company.document_serie_product_ids if fdoc.fiscal_document_id.id == order.fiscal_operation_id.fiscal_document_id.id and fdoc.active]

        if not fiscal_document_serie_ids:
            raise osv.except_osv(_('No fiscal document serie found !'), _("No fiscal document serie found for selected company %s, fiscal operation: '%s' and fiscal documento %s") % (order.company_id.name, order.fiscal_operation_id.code, order.fiscal_operation_id.fiscal_document_id.name))

        journal_ids = [jou for jou in order.fiscal_operation_category_id.journal_ids if jou.company_id.id == obj_company.id]
        if journal_ids:
            journal_id = journal_ids[0].id
        else:
            raise osv.except_osv(_('Error !'),
                _('There is no sales journal defined for this company in Fiscal Operation Category: "%s" (id:%d)') % (order.company_id.name, order.company_id.id))

        for inv_line in obj_invoice_line.browse(cr, uid, lines, context=context):
            if inv_line.product_id.fiscal_type == 'service' or inv_line.product_id.is_on_service_invoice:
                lines_service.append(inv_line.id)

            if inv_line.product_id.fiscal_type == 'product':
                lines_product.append(inv_line.id)

        if lines_service:
            inv_id_service = super(sale_order, self)._make_invoice(cr, uid, order, lines_service, context=None)
            inv_ids.append(inv_id_service)

        if lines_product:
            inv_id_product = super(sale_order, self)._make_invoice(cr, uid, order, lines_product, context=None)
            inv_ids.append(inv_id_product)

        for inv in inv_obj.browse(cr, uid, inv_ids, context=None):

            service_type_id = False
            comment = ''
            fiscal_type = ''
            fiscal_operation_category_id = order.fiscal_operation_category_id
            fiscal_operation_id = order.fiscal_operation_id
            fiscal_position = order.fiscal_position and order.fiscal_position.id

            inv_line_ids = map(lambda x: x.id, inv.invoice_line)

            order_lines = self.pool.get('sale.order.line').search(cr, uid, [('order_id', '=', order.id), ('invoice_lines', 'in', inv_line_ids)], context=context)
            for order_line in self.pool.get('sale.order.line').browse(cr, uid, order_lines, context=context):
                inv_line_id = [inv_line for inv_line in order_line.invoice_lines if inv_line.id in inv_line_ids]
                if inv_line_id:
                    obj_invoice_line.write(cr, uid, inv_line_id[0].id, {
                        'fiscal_operation_category_id': order_line.fiscal_operation_category_id.id or order.fiscal_operation_category_id.id,
                        'fiscal_operation_id': order_line.fiscal_operation_id.id or order.fiscal_operation_id.id,
                        'cfop_id': (order_line.cfop_id and order_line.cfop_id.id) or \
                            (order.fiscal_operation_id and
                             order.fiscal_operation_id.cfop_id and
                             order.fiscal_operation_id.cfop_id.id) or False
                        })

                    if order_line.product_id.fiscal_type == 'service' or inv_line.product_id.is_on_service_invoice:
                        fiscal_operation_category_id = order_line.fiscal_operation_category_id or order.fiscal_operation_category_id or False
                        fiscal_operation_id = order_line.fiscal_operation_id or order.fiscal_operation_id or False
                        service_type_id = (order_line.fiscal_operation_id and order_line.fiscal_operation_id.service_type_id.id) or (order.fiscal_operation_id and order.fiscal_operation_id.service_type_id.id) or False
                        fiscal_type = order_line.product_id.fiscal_type

            if fiscal_operation_id or order.fiscal_operation_id.inv_copy_note:
                comment = fiscal_operation_id and fiscal_operation_id.note or ''

            if order.note:
                comment += ' - ' + order.note

            inv_l10n_br = {'fiscal_operation_category_id': fiscal_operation_category_id and fiscal_operation_category_id.id,
                           'fiscal_operation_id': fiscal_operation_id and fiscal_operation_id.id,
                           'fiscal_document_id': order.fiscal_operation_id.fiscal_document_id.id,
                           'document_serie_id': fiscal_document_serie_ids[0].id,
                           'service_type_id': service_type_id,
                           'fiscal_type': fiscal_type or 'product',
                           'fiscal_position': fiscal_position,
                           'comment': comment,
                           'journal_id': journal_id,
                           }

            inv_obj.write(cr, uid, inv.id, inv_l10n_br, context=context)
            inv_obj.button_compute(cr, uid, [inv.id])
        return inv_id_product or inv_id_service

    def _prepare_order_picking(self, cr, uid, order, context=None):
        result = super(sale_order, self)._prepare_order_picking(cr, uid, order, context)
        result['fiscal_operation_category_id'] = order.fiscal_operation_category_id and order.fiscal_operation_category_id.id
        result['fiscal_operation_id'] = order.fiscal_operation_id and order.fiscal_operation_id.id
        result['fiscal_position'] = order.fiscal_position and order.fiscal_position.id
        return result


sale_order()


class sale_order_line(osv.osv):
    _inherit = 'sale.order.line'

    def _amount_line(self, cr, uid, ids, field_name, arg, context=None):
        tax_obj = self.pool.get('account.tax')
        cur_obj = self.pool.get('res.currency')
        res = {}

        if context is None:
            context = {}
        for line in self.browse(cr, uid, ids, context=context):
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = tax_obj.compute_all(cr, uid, line.tax_id, price, line.product_uom_qty, line.order_id.partner_invoice_id.id, line.product_id, line.order_id.partner_id, fiscal_operation=line.fiscal_operation_id)
            cur = line.order_id.pricelist_id.currency_id
            res[line.id] = cur_obj.round(cr, uid, cur, taxes['total'])
        return res

    _columns = {
        'fiscal_operation_category_id': fields.many2one(
            'l10n_br_account.fiscal.operation.category',
            u'Categoria',
            domain="[('type','=','output'),('use_sale','=',True)]",
            readonly=False,
            states={
                'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]
                }
            ),
        'fiscal_operation_id': fields.many2one(
            'l10n_br_account.fiscal.operation',
            u'Operação Fiscal',
            readonly=False,
            states={
                'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]
                },
            domain="[('fiscal_operation_category_id','=',fiscal_operation_category_id),('type','=','output'),('use_sale','=',True)]"
            ),
        'cfop_id': fields.many2one(
            'l10n_br_account.cfop',
            u'Código Fiscal',
            readonly=False,
            states={
                'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]
                },
            domain="[('type','=','output'),('internal_type','=','normal')]"
            ),
        'fiscal_position': fields.many2one(
            'account.fiscal.position',
            u'Posição Fiscal',
            readonly=False,
            domain="[('fiscal_operation_id','=',fiscal_operation_id)]",
            states={
                'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]
                }
            ),
        'price_subtotal': fields.function(
            _amount_line, string='Subtotal', digits_compute=dp.get_precision('Sale Price')
            ),
        'tax_id': fields.many2many(
            'account.tax', 
            'sale_order_tax', 'order_line_id', 'tax_id', 'Taxes', 
            readonly=False,
            states={
		'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]

                }
            ),
        'product_id': fields.many2one(
            'product.product',
            'Product',
            domain=[('sale_ok', '=', True)],
            change_default=True,
            states={
		'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]

                }
            ),
        'product_uos': fields.many2one(
            'product.uom',
            'Product UoS',
            states={
		'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]

                }
            ),
        'product_packaging': fields.many2one(
            'product.packaging',
            'Packaging',
            states={
		'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]

                }
            ),
        'notes': fields.text(
            'Notes',
            states={
		'done': [('readonly', True)],
                'shipping_except': [('readonly', True)],
                'invoice_except': [('readonly', True)]

                }
 
            ),
        }

    def fiscal_operation_id_change(self, cr, uid, ids, fop_id):
        result = {'value': {} }
        obj_fop = self.pool.get('l10n_br_account.fiscal.operation').browse(cr, uid, fop_id)
        if obj_fop.cfop_id:
            result['value']['cfop_id'] = obj_fop.cfop_id.id
        return result
    
    def product_id_change(self, cr, uid, ids, pricelist, product, qty=0,
                          uom=False, qty_uos=0, uos=False, name='', partner_id=False,
                          lang=False, update_tax=True, date_order=False, packaging=False,
                          fiscal_position=False, flag=False, context=None,
                          fiscal_operation_category_id=False, fiscal_operation_id=False,
                          shop_id=False, parent_fiscal_position=False):

        result = super(sale_order_line, self).product_id_change(cr, uid, ids, pricelist, product, qty,
                                                                uom, qty_uos, uos, name, partner_id,
                                                                lang, update_tax, date_order, packaging,
                                                                fiscal_position, flag, context)

        if not fiscal_operation_category_id or not fiscal_operation_id or not product:
            return result

        product_tmpl_id = self.pool.get('product.product').read(cr, uid, product, ['product_tmpl_id'])['product_tmpl_id'][0]
        default_product_category = self.pool.get('l10n_br_account.product.operation.category').search(cr, uid, [('product_tmpl_id', '=', product_tmpl_id), ('fiscal_operation_category_source_id', '=', fiscal_operation_category_id)])

        if not default_product_category:
            if fiscal_operation_category_id:
                result['value']['fiscal_operation_category_id'] = fiscal_operation_category_id

            if fiscal_operation_id:
                result['value']['fiscal_operation_id'] = fiscal_operation_id

            if fiscal_position:
                result['value']['fiscal_position'] = fiscal_position

            return result

        obj_default_prod_categ = self.pool.get('l10n_br_account.product.operation.category').browse(cr, uid, default_product_category)[0]
        result['value']['fiscal_operation_category_id'] = obj_default_prod_categ.fiscal_operation_category_destination_id.id
        result['value']['fiscal_operation_id'] = False

        #res.parnter address information
        obj_partner = self.pool.get('res.partner').browse(cr, uid, partner_id)
        partner_fiscal_type = obj_partner.partner_fiscal_type_id.id
        to_country = obj_partner.country_id.id
        to_state = obj_partner.state_id.id

        #res.company address information
        obj_shop = self.pool.get('sale.shop').browse(cr, uid, shop_id)
        from_country = obj_shop.company_id.partner_id.country_id.id
        from_state = obj_shop.company_id.partner_id.state_id.id

        fsc_pos_id = self.pool.get('account.fiscal.position.rule').search(cr, uid, ['&', ('company_id', '=', obj_shop.company_id.id), ('fiscal_operation_category_id', '=', obj_default_prod_categ.fiscal_operation_category_destination_id.id), ('use_sale', '=', True), ('fiscal_type', '=', obj_shop.company_id.fiscal_type),
                                                                                    '|', ('from_country', '=', from_country), ('from_country', '=', False),
                                                                                    '|', ('to_country', '=', to_country), ('to_country', '=', False),
                                                                                    '|', ('from_state', '=', from_state), ('from_state', '=', False),
                                                                                    '|', ('to_state', '=', to_state), ('to_state', '=', False),
                                                                                    '|', ('partner_fiscal_type_id', '=', partner_fiscal_type), ('partner_fiscal_type_id', '=', False),
                                                                                    '|', ('to_state', '=', to_state), ('to_state', '=', False),
                                                                                    '|', ('date_start', '=', False), ('date_start', '<=', date_order),
                                                                                    '|', ('date_end', '=', False), ('date_end', '>=', date_order),
                                                                                    '|', ('revenue_start', '=', False), ('revenue_start', '<=', obj_shop.company_id.annual_revenue),
                                                                                    '|', ('revenue_end', '=', False), ('revenue_end', '>=', obj_shop.company_id.annual_revenue),
                                                                                    ])

        if fsc_pos_id:
            obj_fpo_rule = self.pool.get('account.fiscal.position.rule').browse(cr, uid, fsc_pos_id)[0]
            #if fiscal_position != obj_fpo_rule.fiscal_position_id.id:
            #    result['tax_id'] = self.pool.get('account.fiscal.position').map_tax(cr, uid, obj_fpo_rule.fiscal_position_id.id, product_obj.taxes_id)
            #    result['value']['fiscal_position'] = obj_fpo_rule.fiscal_position_id.id
            result['value']['fiscal_operation_id'] = obj_fpo_rule.fiscal_position_id.fiscal_operation_id.id

        return result

    def create_sale_order_line_invoice(self, cr, uid, ids, context=None):
        result = super(sale_order_line, self).create_sale_order_line_invoice(cr, uid, ids, context)
        inv_ids = []
        if result:

            for so_line in self.browse(cr, uid, ids):
                for inv_line in so_line.invoice_lines:
                    if inv_line.invoice_id.state in ('draft'):
                        #FIXME: de onde vem order?
                        company_id = self.pool.get('res.company').browse(cr, uid, order.company_id.id)
                        if not company_id.document_serie_product_ids:
                            #FIXME: de onde vem order?
                            raise osv.except_osv(_('No fiscal document serie found !'), _("No fiscal document serie found for selected company %s and fiscal operation: '%s'") % (order.company_id.name, order.fiscal_operation_id.code))
                        if inv_line.invoice_id.id not in inv_ids:
                            inv_ids.append(inv_line.id)
                            self.pool.get('account.invoice').write(cr, uid, inv_line.invoice_id.id, {'fiscal_operation_category_id': so_line.order_id.fiscal_operation_category_id.id,
                                                                                                     'fiscal_operation_id': so_line.order_id.fiscal_operation_id.id,
                                                                                                     'cfop_id': so_line.order_id.fiscal_operation_id.cfop_id.id,
                                                                                                     'fiscal_document_id': so_line.order_id.fiscal_operation_id.fiscal_document_id.id,
                                                                                                     'document_serie_id': company_id.document_serie_product_ids[0].id})

                        self.pool.get('account.invoice.line').write(cr, uid, inv_line.id, {'cfop_id': so_line.cfop_id.id,
                                                                                           'fiscal_operation_category_id': so_line.fiscal_operation_category_id.id,
                                                                                           'fiscal_operation_id': so_line.fiscal_operation_id.id})

        return result

sale_order_line()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
