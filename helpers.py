
class Paginator:

    PAGE_SIZE = 10

    @staticmethod
    def _has_next(data, page):
        #TODO
        return False

    @staticmethod
    def _has_prev(data, page):
        # TODO
        return False

    def paginate(self, request, data):

        current_page = int(request.args.get('page')) if 'page' in request.args else 0
        base_url = request.base_url

        if not current_page:
            return dict(next=None, prev=None)

        next_page = "%s/?page=%s" % (base_url, current_page + 1) if Paginator()._has_next(data, current_page) else None
        prev_page = "%s/?page=%s" % (base_url, current_page - 1) if Paginator()._has_prev(data, current_page) else None

        response = dict(next=next_page, prev=prev_page)

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

                if type(el[f]) not in [list, int, str, bool, dict, unicode]:
                    eldict[f] = Tools().to_json(el[f], fields=['name', 'id'])
                    continue

                eldict[f] = el[f]

            res.append(eldict)

        return res
