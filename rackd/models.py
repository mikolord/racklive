"""«Сканер»: 3D models of devices made by the user (usually by a neural network from a photo).

A model is plain JSON — no code: a box of the device's real size in millimetres, things drawn on its faces (ports, LEDs, text, vents,
buttons), optional extra blocks (antennas, a stand) and the angle it is shown at. Rack Live draws it with CSS 3D. Everything is checked
strictly here: unknown keys are dropped, numbers must be in range, colours must be #hex, so a model can never carry anything but a picture.
The library lives in data/models.json; a card points to a model by its id (cards entry «model»)."""
import json, os, re, secrets, threading, time

FORMAT, VERSION = 'racklive-model', 1
FACES = ('front', 'back', 'top', 'bottom', 'left', 'right')
KINDS = ('rj45', 'sfp', 'usb', 'power', 'coax', 'other')
MAX_ITEMS, MAX_PARTS, MAX_MODELS, MAX_BYTES = 600, 24, 100, 300_000
HEX = re.compile(r'^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?([0-9a-fA-F]{2})?$')
COLOR_KEYS = ('body', 'front', 'back', 'top', 'side', 'port', 'text', 'led', 'accent')


class Bad(Exception):
    pass


def _num(v, lo, hi, where):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Bad(f'{where}: нужно число')
    if not lo <= v <= hi:
        raise Bad(f'{where}: {v} вне диапазона {lo}…{hi}')
    return round(float(v), 2)


def _color(v, where):
    if not isinstance(v, str) or not HEX.match(v.strip()):
        raise Bad(f'{where}: цвет должен быть вида #3a3d42')
    return v.strip()


def _colors(c, where):
    out = {}
    if c is None:
        return out
    if not isinstance(c, dict):
        raise Bad(f'{where}: нужен объект с цветами')
    for k in COLOR_KEYS:
        if k in c:
            out[k] = _color(c[k], f'{where}.{k}')
    return out


def _face_size(size, face):
    w, h, d = size['w'], size['h'], size['d']
    return {'front': (w, h), 'back': (w, h), 'top': (w, d), 'bottom': (w, d), 'left': (d, h), 'right': (d, h)}[face]


def _item(it, fw, fh, where):
    if not isinstance(it, dict):
        raise Bad(f'{where}: нужен объект')
    t = it.get('type')
    tol = 2
    x, y = _num(it.get('x'), -tol, fw + tol, where + '.x'), _num(it.get('y'), -tol, fh + tol, where + '.y')
    out = {'type': t, 'x': x, 'y': y}
    if t in ('port', 'rect', 'vent'):
        out['w'], out['h'] = _num(it.get('w'), .5, fw + tol, where + '.w'), _num(it.get('h'), .5, fh + tol, where + '.h')
    if t == 'port':
        if it.get('n') is not None:
            out['n'] = int(_num(it.get('n'), 1, 256, where + '.n'))
        kind = it.get('kind', 'rj45')
        if kind not in KINDS:
            raise Bad(f'{where}.kind: одно из {", ".join(KINDS)}')
        out['kind'] = kind
        if it.get('label'):
            out['label'] = str(it['label'])[:24]
    elif t == 'led':
        out['r'] = _num(it.get('r', 1.5), .3, 20, where + '.r')
        if it.get('color'):
            out['color'] = _color(it['color'], where + '.color')
        if it.get('link') is not None:
            out['link'] = int(_num(it.get('link'), 1, 256, where + '.link'))
        out['on'] = bool(it.get('on', True))
    elif t == 'text':
        s = it.get('text')
        if not isinstance(s, str) or not s.strip():
            raise Bad(f'{where}.text: нужен текст')
        out['text'] = s.strip()[:40]
        out['size'] = _num(it.get('size', 4), .8, 80, where + '.size')
        out['weight'] = int(_num(it.get('weight', 600), 300, 900, where + '.weight'))
        if it.get('color'):
            out['color'] = _color(it['color'], where + '.color')
        if it.get('align') in ('left', 'center', 'right'):
            out['align'] = it['align']
    elif t == 'rect':
        if it.get('color'):
            out['color'] = _color(it['color'], where + '.color')
        out['radius'] = _num(it.get('radius', 0), 0, 500, where + '.radius')
    elif t == 'circle':
        out['r'] = _num(it.get('r'), .3, 500, where + '.r')
        if it.get('color'):
            out['color'] = _color(it['color'], where + '.color')
    elif t == 'vent':
        out['slots'] = int(_num(it.get('slots', 8), 1, 120, where + '.slots'))
        out['dir'] = 'v' if it.get('dir') == 'v' else 'h'
    else:
        raise Bad(f'{where}.type: одно из port, led, text, rect, circle, vent')
    return out


def validate(obj):
    """→ (clean model, None) or (None, [понятные ошибки]). The errors are written so they can be pasted back to the neural network."""
    errors = []
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except ValueError as e:
            return None, [f'это не JSON: {e}']
    if not isinstance(obj, dict):
        return None, ['нужен JSON-объект { … }']
    if len(json.dumps(obj, ensure_ascii=False)) > MAX_BYTES:
        return None, [f'модель слишком большая (больше {MAX_BYTES // 1000} КБ)']
    if obj.get('format') != FORMAT:
        errors.append(f'format: должно быть "{FORMAT}"')
    if obj.get('version') != VERSION:
        errors.append(f'version: должно быть {VERSION}')
    out = {'format': FORMAT, 'version': VERSION}
    try:
        name = obj.get('name')
        if not isinstance(name, str) or not name.strip():
            raise Bad('name: нужно название модели')
        out['name'] = name.strip()[:80]
    except Bad as e:
        errors.append(str(e))
    try:
        s = obj.get('size') or {}
        out['size'] = {k: _num(s.get(k), 5, 2500, 'size.' + k) for k in ('w', 'h', 'd')}
    except Bad as e:
        return None, errors + [str(e)]
    try:
        col = obj.get('color') or {}
        if not isinstance(col, dict):
            raise Bad('color: нужен объект {"light": {…}, "dark": {…}}')
        out['color'] = {th: _colors(col.get(th), 'color.' + th) for th in ('light', 'dark') if col.get(th) is not None}
    except Bad as e:
        errors.append(str(e))
    faces, total = {}, 0
    for f, v in (obj.get('faces') or {}).items():
        if f not in FACES:
            errors.append(f'faces.{f}: такой грани нет (есть {", ".join(FACES)})')
            continue
        if not isinstance(v, dict):
            errors.append(f'faces.{f}: нужен объект {{"items": [ … ]}}')
            continue
        fw, fh = _face_size(out['size'], f)
        face = {}
        try:
            if v.get('color'):
                face['color'] = _color(v['color'], f'faces.{f}.color')
        except Bad as e:
            errors.append(str(e))
        items = []
        for i, it in enumerate(v.get('items') or []):
            total += 1
            if total > MAX_ITEMS:
                errors.append(f'слишком много элементов (больше {MAX_ITEMS})')
                break
            try:
                items.append(_item(it, fw, fh, f'faces.{f}.items[{i}]'))
            except Bad as e:
                errors.append(str(e))
        face['items'] = items
        faces[f] = face
    out['faces'] = faces
    parts = []
    for i, p in enumerate((obj.get('parts') or [])[:MAX_PARTS + 1]):
        if i >= MAX_PARTS:
            errors.append(f'parts: не больше {MAX_PARTS} блоков')
            break
        try:
            if not isinstance(p, dict):
                raise Bad(f'parts[{i}]: нужен объект')
            part = {k: _num(p.get(k, 0), -2500, 2500, f'parts[{i}].{k}') for k in ('x', 'y', 'z')}
            part.update({k: _num(p.get(k), .5, 2500, f'parts[{i}].{k}') for k in ('w', 'h', 'd')})
            if p.get('color'):
                part['color'] = _color(p['color'], f'parts[{i}].color')
            if p.get('rx') is not None:
                part['rx'] = _num(p['rx'], -180, 180, f'parts[{i}].rx')
            if p.get('rz') is not None:
                part['rz'] = _num(p['rz'], -180, 180, f'parts[{i}].rz')
            parts.append(part)
        except Bad as e:
            errors.append(str(e))
    out['parts'] = parts
    v = obj.get('view')
    if v is not None:
        try:
            out['view'] = {'rx': _num(v.get('rx', -13), -90, 90, 'view.rx'), 'ry': _num(v.get('ry', -20), -180, 180, 'view.ry')}
        except (Bad, AttributeError) as e:
            errors.append(str(e) if isinstance(e, Bad) else 'view: нужен объект {"rx": …, "ry": …}')
    if errors:
        return None, errors[:30]
    return out, None


FREE_TASK = """
ВАЖНО: в этом варианте порты НЕ привязываются к номерам. Человек хочет красивую, интересную модель, а какой разъём каким портом
считать, он отметит сам в Rack Live (нажмёт на гранях модели). Поэтому:
  — рисуй разъёмы как "port" БЕЗ поля "n", а у индикаторов "led" не пиши "link";
  — всё равно ставь разъёмы на их настоящие места и настоящего размера, чтобы их было легко узнать и отметить;
  — можешь смелее добавлять детали: подставки, антенны, панели, надписи, экраны, решётки.
"""
FREE_PORTS = """
           В ЭТОМ ВАРИАНТЕ поле "n" у портов НЕ пиши: номера человек отметит сам."""


class Library:
    """data/models.json: [{id, name, model, t}]"""
    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, 'models.json')
        self.lock = threading.Lock()
        try:
            with open(self.path, encoding='utf-8') as f:
                self.items = [m for m in json.load(f) if isinstance(m, dict) and m.get('id') and m.get('model')]
        except (OSError, ValueError):
            self.items = []

    def _save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.items, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def public(self):
        return [{'id': m['id'], 'name': m['name'], 'model': m['model']} for m in self.items]

    def add(self, model, mid=None):
        with self.lock:
            if mid and any(m['id'] == mid for m in self.items):            # replacing a model keeps its id: the cards that use it stay
                for m in self.items:
                    if m['id'] == mid:
                        m.update(name=model['name'], model=model, t=int(time.time()))
            else:
                if len(self.items) >= MAX_MODELS:
                    raise ValueError(f'в библиотеке уже {MAX_MODELS} моделей, удалите ненужные')
                mid = secrets.token_hex(4)
                self.items.append({'id': mid, 'name': model['name'], 'model': model, 't': int(time.time())})
            self._save()
            return mid

    def remove(self, mid):
        with self.lock:
            self.items = [m for m in self.items if m['id'] != mid]
            self._save()


EXAMPLE = {
    "format": FORMAT, "version": VERSION,
    "name": "Keenetic Ultra (KN-1811)",
    "size": {"w": 214, "h": 33, "d": 160},
    "color": {"light": {"body": "#f1f2f4", "port": "#202327", "text": "#5b6168", "led": "#3d8bff"},
              "dark": {"body": "#1d1f22", "port": "#050506", "text": "#a7adb5", "led": "#3d8bff"}},
    "faces": {
        "front": {"items": [
            {"type": "text", "x": 12, "y": 13, "text": "KEENETIC", "size": 5, "weight": 700},
            {"type": "led", "x": 150, "y": 16.5, "r": 1.4, "on": True},
            {"type": "led", "x": 160, "y": 16.5, "r": 1.4, "link": 0 or None},
            {"type": "circle", "x": 196, "y": 16.5, "r": 3.5, "color": "#c9ccd1"}]},
        "back": {"items": [
            {"type": "port", "n": 0 or None, "kind": "power", "x": 14, "y": 11, "w": 9, "h": 9},
            {"type": "port", "n": 5, "kind": "rj45", "x": 40, "y": 9, "w": 15, "h": 13, "label": "WAN"},
            {"type": "port", "n": 1, "kind": "rj45", "x": 66, "y": 9, "w": 15, "h": 13},
            {"type": "port", "n": 2, "kind": "rj45", "x": 84, "y": 9, "w": 15, "h": 13},
            {"type": "port", "n": 3, "kind": "rj45", "x": 102, "y": 9, "w": 15, "h": 13},
            {"type": "port", "n": 4, "kind": "rj45", "x": 120, "y": 9, "w": 15, "h": 13},
            {"type": "port", "kind": "usb", "x": 146, "y": 12, "w": 12, "h": 5},
            {"type": "vent", "x": 168, "y": 8, "w": 36, "h": 16, "slots": 8, "dir": "v"}]},
        "top": {"items": [{"type": "vent", "x": 20, "y": 20, "w": 174, "h": 60, "slots": 18}]}
    },
    "parts": [
        {"x": -80, "y": -55, "z": -60, "w": 10, "h": 90, "d": 10},
        {"x": 80, "y": -55, "z": -60, "w": 10, "h": 90, "d": 10}
    ],
    "view": {"rx": -14, "ry": 160}
}
# the example must be valid JSON without Python-only values
for _f in EXAMPLE['faces'].values():
    for _it in _f['items']:
        for _k in [k for k, v in _it.items() if v is None]:
            del _it[_k]


def free_example():
    """the same router drawn as a picture only: sockets without numbers (the user marks the ports in Rack Live)"""
    ex = json.loads(json.dumps(EXAMPLE))
    for f in ex['faces'].values():
        for it in f['items']:
            it.pop('n', None); it.pop('link', None)
    return ex


def guide_text(free=False):
    """free=True: the user wants an interesting model and will mark the ports in Rack Live himself — no port numbers in the JSON"""
    ex = json.dumps(free_example() if free else EXAMPLE, ensure_ascii=False, indent=2)
    return f"""ИНСТРУКЦИЯ ДЛЯ НЕЙРОСЕТИ: 3D-МОДЕЛЬ УСТРОЙСТВА ДЛЯ RACK LIVE{' (ПОРТЫ ОТМЕТИТ ЧЕЛОВЕК)' if free else ''}

Rack Live — панель мониторинга домашней сети (https://github.com/mikolord/racklive). В приложении «Сканер» человек наводит камеру на
QR-наклейку на устройстве, и открывается его карточка с объёмной моделью. Порты на модели нажимаются: показывается, что в них воткнуто.

Твоя задача: по фото, названию или описанию устройства составить его модель в формате JSON, описанном ниже.{FREE_TASK if free else ''}
Это ТОЛЬКО данные: никакого кода, HTML, SVG, CSS, ссылок и картинок внутри быть не может. Rack Live сам нарисует модель из этих данных.
Ответь одним JSON-объектом, без пояснений и без комментариев внутри (в JSON комментарии запрещены).

1. КОРПУС
Модель — прямоугольный корпус настоящего размера в миллиметрах:
  "size": {{"w": ширина, "h": высота, "d": глубина}} (от 5 до 2500 мм).
Стоечное оборудование 19″: ширина 440 мм (с ушами 482), высота 1U = 44 мм, 2U = 88 мм.
Если точных размеров не знаешь — оцени по фото и пропорциям; ошибка в несколько миллиметров не страшна.

2. ГРАНИ
"faces" содержит грани: front (лицо), back (зад), top (верх), bottom (низ), left, right. Можно описать только нужные.
У каждой грани "items" — список элементов на ней. Координаты в миллиметрах от ЛЕВОГО ВЕРХНЕГО угла грани, как если смотреть
прямо на эту грань снаружи. Размеры граней: front и back — w×h, top и bottom — w×d, left и right — d×h.
x, y — левый верхний угол элемента (у led и circle — центр).

3. ЭЛЕМЕНТЫ
  port   — разъём. Поля: x, y, w, h, kind (rj45 | sfp | usb | power | coax | other), n (номер порта, как его считает
           устройство: 1, 2, 3…; у порта без номера n не пишется), label (короткая подпись, напр. "WAN", необязательно).
           Типичные размеры: RJ45 15×13 мм, SFP 14×9 мм, USB-A 12×5 мм.{FREE_PORTS if free else ''}
           ВАЖНО: все порты одного вида одного размера, ставь их ровно в ряд и с одинаковым шагом, как на настоящем устройстве.
           У коммутаторов нечётные порты обычно сверху, чётные снизу (1 над 2, 3 над 4…) — проверь по фото.
  led    — индикатор. x, y (центр), r (радиус, обычно 1–2 мм), color (необязательно), link (номер порта: горит, когда на нём есть линк),
           on (true/false — горит ли, если link не указан).
  text   — надпись. x, y, text (до 40 знаков), size (высота букв, мм), weight (400–800), color, align (left | center | right).
  rect   — плоский прямоугольник (панель, наклейка, экран). x, y, w, h, color, radius.
  circle — круг (кнопка, винт). x, y (центр), r, color.
  vent   — вентиляционная решётка. x, y, w, h, slots (число прорезей), dir (h — горизонтальные, v — вертикальные).

4. ДОПОЛНИТЕЛЬНЫЕ БЛОКИ (необязательно)
"parts" — до {MAX_PARTS} простых брусков: антенны, ножки, подставка, блок питания. Поля: x, y, z — смещение ЦЕНТРА бруска от центра
корпуса в мм (x вправо, y ВНИЗ, z к зрителю — от лицевой грани наружу), w, h, d — размеры, color, rx и rz — наклон в градусах.
Антенна сзади над корпусом: y отрицательный (выше), z отрицательный (за корпусом).

5. ЦВЕТА
"color": {{"light": {{…}}, "dark": {{…}}}} — цвета для светлой и тёмной темы приложения. Ключи: body (корпус), front, back, top, side,
port (гнёзда), text, led, accent. Только формат #rrggbb. Если не указать, Rack Live возьмёт свои строгие цвета:
белый алюминий в светлой теме и чёрный — в тёмной. Это лучше всего, если устройство не яркого цвета.

6. С КАКОЙ СТОРОНЫ ПОКАЗЫВАТЬ
"view": {{"rx": наклон, "ry": поворот}} в градусах. rx от -90 до 90 (отрицательный — смотрим сверху), ry от -180 до 180
(0 — лицом к зрителю, 180 — задом). Если порты на задней грани (как у домашних роутеров), поставь ry около 160–200,
чтобы порты было видно сразу. Пользователь потом сможет повернуть модель и зафиксировать своё положение.

7. ОБЯЗАТЕЛЬНЫЕ ПОЛЯ
"format": "{FORMAT}", "version": {VERSION}, "name": название модели, "size".

8. ОГРАНИЧЕНИЯ
Не больше {MAX_ITEMS} элементов на всех гранях, не больше {MAX_PARTS} блоков, файл до {MAX_BYTES // 1000} КБ. Числа — обычные числа (не строки).
Если что-то не подходит, Rack Live покажет список ошибок — исправь именно их и пришли модель целиком заново.

9. ПРИМЕР (домашний роутер, порты сзади, две антенны{', разъёмы без номеров' if free else ''})
{ex}

Пришли только JSON-модель."""
