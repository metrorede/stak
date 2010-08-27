# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005-2007 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s):   Bruno Rafael Garcia         <brg@async.com.br>
##              Evandro Vale Miquelito      <evandro@async.com.br>
##              Johan Dahlin                <jdahlin@async.com.br>
##              Fabio Morbec                <fabio@async.com.br>
##
""" Search dialogs for product objects """

from decimal import Decimal

import gtk
from kiwi.datatypes import currency
from kiwi.enums import SearchFilterPosition
from kiwi.db.query import DateQueryState, DateIntervalQueryState
from kiwi.ui.search import ComboSearchFilter, DateSearchFilter, Today
from kiwi.ui.objectlist import Column, ColoredColumn, SearchColumn

from stoqlib.database.orm import AND
from stoqlib.domain.person import PersonAdaptToBranch
from stoqlib.domain.product import Product
from stoqlib.domain.sellable import Sellable
from stoqlib.domain.views import (ProductFullStockView, ProductQuantityView,
                                  ProductFullStockItemView, SoldItemView)
from stoqlib.gui.base.gtkadds import change_button_appearance
from stoqlib.gui.base.search import (SearchDialog, SearchEditor,
                                     SearchDialogPrintSlave)
from stoqlib.gui.editors.producteditor import (ProductEditor,
                                               ProductStockEditor)
from stoqlib.gui.printing import print_report
from stoqlib.lib.defaults import sort_sellable_code
from stoqlib.lib.translation import stoqlib_gettext
from stoqlib.lib.validators import format_quantity, get_formatted_cost
from stoqlib.reporting.product import (ProductReport, ProductQuantityReport,
                                       ProductPriceReport,
                                       ProductStockReport,
                                       ProductsSoldReport)

_ = stoqlib_gettext


class ProductSearch(SearchEditor):
    title = _('Product Search')
    table = Product
    size = (775, 450)
    search_table = ProductFullStockView
    editor_class = ProductEditor
    footer_ok_label = _('Add products')
    searchbar_result_strings = (_('product'), _('products'))

    def __init__(self, conn, hide_footer=True, hide_toolbar=False,
                 selection_mode=gtk.SELECTION_BROWSE,
                 hide_cost_column=False, use_product_statuses=None,
                 hide_price_column=False):
        """
        Create a new ProductSearch object.
        @param conn: a orm Transaction instance
        @param hide_footer: do I have to hide the dialog footer?
        @param hide_toolbar: do I have to hide the dialog toolbar?
        @param selection_mode: the kiwi list selection mode
        @param hide_cost_column: if it's True, no need to show the
                                 column 'cost'
        @param use_product_statuses: a list instance that, if provided, will
                                     overwrite the statuses list defined in
                                     get_filter_slave method
        @param hide_price_column: if it's True no need to show the
                                  column 'price'
        """
        self.use_product_statuses = use_product_statuses
        self.hide_cost_column = hide_cost_column
        self.hide_price_column = hide_price_column
        SearchEditor.__init__(self, conn, hide_footer=hide_footer,
                              hide_toolbar=hide_toolbar,
                              selection_mode=selection_mode)
        self.set_searchbar_labels(_('matching'))
        self.set_edit_button_sensitive(False)
        self.results.connect('selection-changed', self.on_selection_changed)
        self._setup_print_slave()

    def _setup_print_slave(self):
        self._print_slave = SearchDialogPrintSlave()
        change_button_appearance(self._print_slave.print_price_button,
                                 gtk.STOCK_PRINT, _("_Table of Price"))
        self.attach_slave('print_holder', self._print_slave)
        self._print_slave.connect('print', self.on_print_price_button_clicked)
        self._print_slave.print_price_button.set_sensitive(False)
        self.results.connect('has-rows', self._has_rows)

    def on_print_button_clicked(self, button):
        print_report(ProductReport, self.results,
                     filters=self.search.get_search_filters(),
                     branch_name=self.branch_filter.combo.get_active_text())

    def on_print_price_button_clicked(self, button):
        print_report(ProductPriceReport, list(self.results),
                     filters = self.search.get_search_filters(),
                     branch_name=self.branch_filter.combo.get_active_text())

    def _has_rows(self, results, obj):
        SearchEditor._has_rows(self, results, obj)
        self._print_slave.print_price_button.set_sensitive(obj)

    #
    # SearchDialog Hooks
    #

    def create_filters(self):
        self.set_text_field_columns(['description', 'barcode',
                                     'category_description'])
        self.executer.set_query(self.executer_query)

        # Branch
        branch_filter = self.create_branch_filter(_('In branch:'))
        branch_filter.select(None)
        self.add_filter(branch_filter, columns=[])
        self.branch_filter = branch_filter

        # Status
        statuses = [(desc, id) for id, desc in Sellable.statuses.items()]
        statuses.insert(0, (_('Any'), None))
        status_filter = ComboSearchFilter(_('with status:'), statuses)
        status_filter.select(None)
        self.add_filter(status_filter, columns=['status'],
                        position=SearchFilterPosition.TOP)

    #
    # SearchEditor Hooks
    #

    def get_editor_model(self, product_full_stock_view):
        return product_full_stock_view.product

    def get_columns(self):
        cols = [SearchColumn('code', title=_('Code'), data_type=str,
                              sort_func=sort_sellable_code,
                              sorted=True, width=130),
                SearchColumn('barcode', title=_('Barcode'), data_type=str,
                             width=130),
                SearchColumn('category_description', title=_(u'Category'),
                             data_type=str, width=100),
                SearchColumn('description', title=_(u'Description'),
                             expand=True, data_type=str),
                SearchColumn('location', title=_('Location'), data_type=str,
                              visible=False)]
        # The price/cost columns must be controlled by hide_cost_column and
        # hide_price_column. Since the product search will be available across
        # the applications, it's important to restrict such columns depending
        # of the context.
        if not self.hide_cost_column:
            cols.append(SearchColumn('cost', _('Cost'), data_type=currency,
                                     format_func=get_formatted_cost, width=90))
        if not self.hide_price_column:
            cols.append(SearchColumn('price', title=_('Price'),
                                     data_type=currency, width=90))

        cols.append(SearchColumn('stock', title=_('Stock Total'),
                                 format_func=format_quantity,
                                 data_type=Decimal, width=100))
        return cols

    def executer_query(self, query, having, conn):
        branch = self.branch_filter.get_state().value
        if branch is not None:
            branch = PersonAdaptToBranch.get(branch, connection=conn)
        return self.search_table.select_by_branch(query, branch,
                                                  connection=conn)

    def on_selection_changed(self, results, selected):
        can_edit = bool(selected)
        self.set_edit_button_sensitive(can_edit)


def format_data(data):
    # must return zero or report printed show None instead of 0
    if data is None:
        return 0
    return format_quantity(data)


class ProductSearchQuantity(SearchDialog):
    title = _('Product History Search')
    size = (775, 450)
    table = search_table = ProductQuantityView
    advanced_search = False
    show_production_columns = False

    def on_print_button_clicked(self, button):
        print_report(ProductQuantityReport, self.results,
                     filters=self.search.get_search_filters())

    #
    # SearchDialog Hooks
    #

    def create_filters(self):
        self.set_text_field_columns(['description'])

        # Date
        date_filter = DateSearchFilter(_('Date:'))
        date_filter.select(Today)
        self.add_filter(date_filter, columns=['sold_date', 'received_date',
                                              'production_date'])

        # Branch
        branch_filter = self.create_branch_filter(_('In branch:'))
        self.add_filter(branch_filter, columns=['branch'],
                        position=SearchFilterPosition.TOP)
        # remove 'Any' option from branch_filter
        branch_filter.combo.remove_text(0)

    #
    # SearchEditor Hooks
    #

    def get_columns(self):
        return [Column('code', title=_('Code'), data_type=str,
                       sort_func=sort_sellable_code,
                       sorted=True, width=130),
                Column('description', title=_('Description'), data_type=str,
                       expand=True),
                Column('quantity_sold', title=_('Sold'),
                       format_func=format_data, data_type=Decimal,
                       visible=not self.show_production_columns),
                Column('quantity_transfered', title=_('Transfered'),
                       format_func=format_data, data_type=Decimal,
                       visible=not self.show_production_columns),
                Column('quantity_retained', title=_('Retained'),
                       format_func=format_data, data_type=Decimal,
                       visible=not self.show_production_columns),
                Column('quantity_received', title=_('Received'),
                       format_func=format_data, data_type=Decimal,
                       visible=not self.show_production_columns),
                Column('quantity_produced', title=_('Produced'),
                       format_func=format_data, data_type=Decimal,
                       visible=self.show_production_columns),
                Column('quantity_consumed', title=_('Consumed'),
                       format_func=format_data, data_type=Decimal,
                       visible=self.show_production_columns),
                Column('quantity_lost', title=_('Lost'),
                       format_func=format_data, data_type=Decimal,
                       visible=self.show_production_columns,)]


class ProductsSoldSearch(SearchDialog):
    title = _('Products Sold Search')
    size = (775, 450)
    table = search_table = SoldItemView
    advanced_search = False

    def on_print_button_clicked(self, button):
        print_report(ProductsSoldReport, self.results,
                     filters=self.search.get_search_filters())

    #
    # SearchDialog Hooks
    #

    def create_filters(self):
        self.set_text_field_columns(['description'])
        self.executer.set_query(self.executer_query)

        # Date
        date_filter = DateSearchFilter(_('Date:'))
        date_filter.select(Today)
        self.add_filter(date_filter)
        self.date_filter = date_filter

        # Branch
        branch_filter = self.create_branch_filter(_('In branch:'))
        branch_filter.select(None)
        self.add_filter(branch_filter, columns=[],
                        position=SearchFilterPosition.TOP)
        self.branch_filter = branch_filter

    def executer_query(self, query, having, conn):
        # We have to do this manual filter since adding this columns to the
        # view would also group the results by those fields, leading to
        # duplicate values in the results.
        branch = self.branch_filter.get_state().value
        if branch is not None:
            branch = PersonAdaptToBranch.get(branch, connection=conn)

        date = self.date_filter.get_state()
        if isinstance(date, DateQueryState):
            date = date.date
        elif isinstance(date, DateIntervalQueryState):
            date = (date.start, date.end)

        return self.table.select_by_branch_date(query, branch, date,
                                           connection=conn)
    #
    # SearchEditor Hooks
    #

    def get_columns(self):
        return [Column('code', title=_('Code'), data_type=str,
                       sorted=True, width=130),
                Column('description', title=_('Description'), data_type=str,
                       expand=True),
                Column('quantity', title=_('Sold'),
                       format_func=format_data,
                       data_type=Decimal),
                Column('average_cost', title=_('Avg. Cost'),
                       data_type=currency),
               ]


class ProductStockSearch(SearchEditor):
    title = _('Product Stock Search')
    size = (800, 450)
    table = search_table = ProductFullStockItemView
    editor_class = ProductStockEditor
    has_new_button = False
    searchbar_result_strings = (_('product'), _('products'))
    advanced_search = True

    #
    # SearchDialog Hooks
    #

    def create_filters(self):
        self.set_text_field_columns(['description', 'category_description'])

    def on_print_button_clicked(self, widget):
        print_report(ProductStockReport, self.results,
                     filters=self.search.get_search_filters())

    #
    # SearchEditor Hooks
    #

    def get_editor_model(self, model):
        return model.product

    def get_columns(self):
        return [SearchColumn('code', title=_('Code'), data_type=str,
                             sort_func=sort_sellable_code,
                             width=80),
                SearchColumn('category_description', title=_('Category'),
                             data_type=str, width=120),
                SearchColumn('description', title=_('Description'), data_type=str,
                             expand=True, sorted=True),
                SearchColumn('location', title=_('Location'), data_type=str,
                             visible=False),
                SearchColumn('maximum_quantity', title=_('Maximum'),
                             visible=False, format_func=format_data,
                             data_type=Decimal),
                SearchColumn('minimum_quantity', title=_('Minimum'),
                             format_func=format_data, data_type=Decimal),
                SearchColumn('stock', title=_('In Stock'),
                             format_func=format_data, data_type=Decimal),
                SearchColumn('to_receive_quantity', title=_('To Receive'),
                              format_func=format_data, data_type=Decimal),
                ColoredColumn('difference', title=_('Difference'), color='red',
                              format_func=format_data, data_type=Decimal,
                              data_func=lambda x: x <= Decimal(0)),]


class ProductPurchaseSearch(SearchDialog):
    title = _('Product Stock Search')
    size = (800, 450)
    has_new_button = False

    def __init__(self, conn, selection_mode=gtk.SELECTION_BROWSE,
                 search_str=None, query=None,
                 hide_footer=False, double_click_confirm=True,
                 table=None
                 ):
        self._query = query

        SearchDialog.__init__(self, conn, selection_mode=selection_mode,
                           hide_footer=hide_footer, table=table,
                           double_click_confirm=double_click_confirm)
        if search_str:
            self.set_searchbar_search_string(search_str)
            self.search.refresh()

    def get_columns(self):
        return [SearchColumn('barcode', title=_('Barcode'), data_type=str,
                             sort_func=sort_sellable_code,
                             width=80),
                SearchColumn('category_description', title=_('Category'),
                             data_type=str, width=120),
                SearchColumn('description', title=_('Description'), data_type=str,
                             expand=True, sorted=True),
              ]


    def update_widgets(self):
        sellable_view = self.results.get_selected()
        self.ok_button.set_sensitive(bool(sellable_view))

    def create_filters(self):
        self.set_text_field_columns(['description', 'barcode',
                                     'category_description'])
        self.executer.set_query(self.executer_query)

        # Branch
        #branch_filter = self.create_branch_filter(_('In branch:'))
        #branch_filter.select(None)
        #self.add_filter(branch_filter, columns=[])
        #self.branch_filter = branch_filter

        # Status
        #statuses = [(desc, id) for id, desc in Sellable.statuses.items()]
        #statuses.insert(0, (_('Any'), None))
        #status_filter = ComboSearchFilter(_('with status:'), statuses)
        #status_filter.select(None)
        #self.add_filter(status_filter, columns=['status'],
        #                position=SearchFilterPosition.TOP)

    def executer_query(self, query, having, conn):
        new_query = self._query
        if query:
            new_query = AND(query, new_query)

        return self.search_table.select(new_query, connection=conn)

