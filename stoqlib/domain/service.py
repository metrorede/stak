# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005,2006 Async Open Source <http://www.async.com.br>
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
## Author(s): Henrique Romano           <henrique@async.com.br>
##            Evandro Vale Miquelito    <evandro@async.com.br>
##
""" Base classes to manage services informations """

import datetime

from sqlobject import (UnicodeCol, DateTimeCol, ForeignKey, SQLObject,
                       IntCol, BLOBCol)
from kiwi.argcheck import argcheck
from kiwi.datatypes import currency
from zope.interface import implements

from stoqlib.database.columns import DecimalCol, PriceCol
from stoqlib.lib.translation import stoqlib_gettext
from stoqlib.exceptions import SellError, DatabaseInconsistency
from stoqlib.domain.base import Domain, ModelAdapter, BaseSQLView
from stoqlib.domain.sellable import AbstractSellable, AbstractSellableItem
from stoqlib.domain.interfaces import ISellable, IDelivery, IContainer
from stoqlib.domain.product import ProductSellableItem

_ = stoqlib_gettext

#
# Base Domain Classes
#


class Service(Domain):
    """Class responsible to store basic service informations."""

    image = BLOBCol(default='')


class ServiceSellableItem(AbstractSellableItem):
    """A service implementation as a sellable item."""

    notes = UnicodeCol(default=None)
    estimated_fix_date = DateTimeCol(default=datetime.datetime.now)
    completion_date = DateTimeCol(default=None)


    #
    # Auxiliary methods
    #

    def sell(self):
        conn = self.get_connection()
        if not self.sellable.can_be_sold():
            msg = '%s is already sold' % self.get_adapted()
            raise SellError(msg)

class DeliveryItem(Domain):
    """Class responsible to store all the products for a certain delivery"""

    quantity = DecimalCol()
    sellable = ForeignKey('AbstractSellable')
    delivery = ForeignKey('ServiceSellableItemAdaptToDelivery')

    #
    # Accessors
    #

    def get_price(self):
        return self.sellable.price

    def get_total(self):
        return currency(self.get_price() * self.quantity)

#
# Adapters
#


class ServiceSellableItemAdaptToDelivery(ModelAdapter):
    """A service implementation as a delivery facet."""

    implements(IDelivery, IContainer)

    address = UnicodeCol(default='')

    #
    # IContainer implementation
    #

    def add_item(self, item):
        if not isinstance(item, ProductSellableItem):
            raise TypeError("Received a %s object, expected %s."
                            % (type(item), ProductSellableItem))

        conn = self.get_connection()
        obj = item.sellable
        sellable = type(obj).get(obj.id, connection=conn)
        quantity = item.quantity - item.get_quantity_delivered()
        return DeliveryItem(connection=conn, sellable=sellable,
                            delivery=self, quantity=quantity)

    def get_items(self):
        return DeliveryItem.selectBy(connection=self.get_connection(),
                                     deliveryID=self.id)

    def remove_item(self, items):
        for item in items:
            if not isinstance(item, DeliveryItem):
                raise TypeError('Invalid type for delivery item, it should '
                                'be DeliveryItem, got %s instead'
                                % type(item))
            conn = item.get_connection()
            DeliveryItem.delete(item.id, connection=conn)

    #
    # General methods
    #

    @argcheck(AbstractSellable)
    def get_item_by_sellable(self, sellable):
        items = [item for item in self.get_items()
                    if item.sellable.id == sellable.id]
        qty = len(items)
        if not qty:
            return
        if qty > 1:
            raise DatabaseInconsistency('You should have only one item for '
                                        'this sellable, fot %d instead'
                                        % qty)
        return items[0]

ServiceSellableItem.registerFacet(ServiceSellableItemAdaptToDelivery,
                                  IDelivery)


class ServiceAdaptToSellable(AbstractSellable):
    """A service implementation as a sellable facet."""

    sellableitem_table = ServiceSellableItem

    def _create(self, id, **kw):
        if 'status' not in kw:
            kw['status'] = AbstractSellable.STATUS_AVAILABLE
        AbstractSellable._create(self, id, **kw)

Service.registerFacet(ServiceAdaptToSellable, ISellable)


#
# Views
#


class ServiceView(SQLObject, BaseSQLView):
    """Stores service informations """
    code = IntCol()
    barcode = UnicodeCol()
    status = IntCol()
    cost = PriceCol()
    price = PriceCol()
    description = UnicodeCol()
    unit = UnicodeCol()
    service_id = IntCol()

    def get_unit(self):
        return self.unit or u""
