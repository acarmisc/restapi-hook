import logging
from openerp.osv import fields as odoo_fields


_logger = logging.getLogger(__name__)

class Paginator:

    # TODO: get configured value from DB?

    PAGE_SIZE = 10

    def paginate(self, request, totalcount):

        current_page = int(request.args.get('page')) if 'page' in request.args else 0
        base_url = request.base_url

        original_query = ''
        for k, v in request.args.items():
            if k != 'page': original_query += '&%s=%s' % (k, v)

        if not current_page:
            return dict(next=None, prev=None)

        offset = self.PAGE_SIZE * (current_page - 1)
        limit = self.PAGE_SIZE * current_page

        is_last = True if limit >= totalcount else False

        next_page = "%s/?%s&page=%s" % (base_url, original_query, current_page + 1) if not is_last else None
        prev_page = "%s/?%s&page=%s" % (base_url, original_query, current_page - 1) if current_page > 1 else None

        response = dict(next=next_page, prev=prev_page, offset=offset, limit=limit, count=totalcount)

        return response


class Tools:

    @staticmethod
    def to_json(obj, fields=None):
        res = list()

        if not fields:
            fields = obj.fields_get_keys() if not hasattr(obj, '_jsonfields') else obj._jsonfields.split(',')

        for el in obj:
            eldict = dict()

            for f in fields:
                if f not in el.fields_get_keys():
                    continue

                if type(el[f]) not in [list, int, str, bool, dict, unicode, float]:
                    if hasattr(el[f], '_jsonfields'):
                        eldict[f] = Tools().to_json(el[f], fields=el[f]._jsonfields.split(','))
                    else:
                        eldict[f] = Tools().to_json(el[f], fields=['name', 'id'])
                    continue

                if not el[f] and type(obj._columns.get(f)) is not odoo_fields.boolean:
                    eldict[f] = None
                else:
                    eldict[f] = el[f]

            res.append(eldict)

        return res
