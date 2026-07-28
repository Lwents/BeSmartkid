from urllib.parse import urlencode

from rest_framework.exceptions import ValidationError


def positive_int_query(request, name, default, *, aliases=(), maximum=None):
    raw_value = None
    used_name = name
    for candidate in (name, *aliases):
        if candidate in request.query_params:
            raw_value = request.query_params.get(candidate)
            used_name = candidate
            break
    if raw_value is None or str(raw_value).strip() == '':
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise ValidationError({used_name: 'Giá trị phải là số nguyên dương.'})
    if value < 1:
        raise ValidationError({used_name: 'Giá trị phải lớn hơn hoặc bằng 1.'})
    if maximum is not None and value > maximum:
        raise ValidationError({used_name: f'Giá trị không được vượt quá {maximum}.'})
    return value


def page_link(request, page):
    if page is None:
        return None
    params = request.query_params.copy()
    params['page'] = page
    return request.build_absolute_uri(f'{request.path}?{urlencode(params, doseq=True)}')
