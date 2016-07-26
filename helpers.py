
class Paginator:

    PAGE_SIZE = 2

    def paginate(self, request, totalcount):

        current_page = int(request.args.get('page')) if 'page' in request.args else 0
        base_url = request.base_url

        if not current_page:
            return dict(next=None, prev=None)

        offset = self.PAGE_SIZE * (current_page - 1)
        limit = self.PAGE_SIZE * current_page

        is_last = True if limit >= totalcount else False

        next_page = "%s/?page=%s" % (base_url, current_page + 1) if not is_last else None
        prev_page = "%s/?page=%s" % (base_url, current_page - 1) if current_page > 1 else None

        response = (next=next_page, prev=prev_page, offset=offset, limit=limit, count=totalcount)

        return response


class Tools:

    @staticmethod
    def to_json(obj, fields=None):
        res = list()

        if not fields:
            fields = obj.fields_get_keys()

        for el in obj:
            eldict = dict()

            for f in fields:
                if f not in el.fields_get_keys():
                    continue

                if type(el[f]) not in [list, int, str, bool, dict, unicode, float]:
                    eldict[f] = Tools().to_json(el[f], fields=['name', 'id'])
                    continue

                eldict[f] = el[f]

            res.append(eldict)

        return res
