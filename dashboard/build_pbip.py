import json
import re
import uuid
from pathlib import Path

_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric'
_VISUAL_SCHEMA = f'{_SCHEMA}/item/report/definition/visualContainer/2.12.0/schema.json'
_PAGE_SCHEMA = f'{_SCHEMA}/item/report/definition/page/2.1.0/schema.json'
_PAGE_W, _PAGE_H = 1280, 720
_BASE_THEME = 'CY24SU10'
_THEME_FILE = 'IFAD_Corporate.json'
_ASSETS = Path(__file__).parent / 'pbip_assets'
_FONT = "'wf_standard-font, helvetica, arial, sans-serif'"
_IFAD_BLUE = '#003FBC'
_IFAD_TEAL = '#009999'

PG_SERVER = 'localhost:5433'
PG_DATABASE = 'iot'
OUT_DIR = Path(__file__).parent
NAME = 'IoTPipeline'

LOCATION_COLORS = {
    'warehouse-A': '#003FBC',
    'warehouse-B': '#2D2D8A',
    'cold-storage': '#009999',
    'office': '#99CC00',
}


def _tag() -> str:
    return str(uuid.uuid4())


def _lit(value: str) -> dict:
    return {'expr': {'Literal': {'Value': value}}}


def _text_lit(text: str) -> dict:
    return _lit("'" + text.replace("'", "''") + "'")


def _field(entity: str, prop: str, kind: str) -> dict:
    return {kind: {'Expression': {'SourceRef': {'Entity': entity}}, 'Property': prop}}


def _col(entity: str, prop: str):
    return entity, prop, 'Column'


def _mea(entity: str, prop: str):
    return entity, prop, 'Measure'


def _proj(ref) -> dict:
    entity, prop, kind = ref
    return {'field': _field(entity, prop, kind), 'queryRef': f'{entity}.{prop}', 'nativeQueryRef': prop}


def _theme_color(color_id: int, percent: float) -> dict:
    return {'solid': {'color': {'expr': {'ThemeDataColor': {'ColorId': color_id, 'Percent': percent}}}}}


def _color(hex_code: str) -> dict:
    return {'solid': {'color': _lit(f"'{hex_code}'")}}


def _styled_title(text: str, size: int = 14, *, bold: bool = False, align: str = 'left') -> list:
    return [{'properties': {
        'show': _lit('true'),
        'text': _text_lit(text),
        'fontFamily': _lit(_FONT),
        'fontSize': _lit(f'{size}D'),
        'bold': _lit('true' if bold else 'false'),
        'alignment': _text_lit(align),
        'fontColor': _theme_color(1, 0),
        'titleWrap': _lit('true'),
    }}]


def _panel(title: str | None, *, title_size: int = 13) -> dict:
    container = {
        'background': [{'properties': {'show': _lit('true'), 'transparency': _lit('0D')}}],
        'border': [{'properties': {'show': _lit('true'), 'color': _color('#E2E2E2'), 'radius': _lit('6D')}}],
        'dropShadow': [{'properties': {'show': _lit('false')}}],
    }
    if title:
        container['title'] = _styled_title(title, title_size, align='left')
    return container


class Page:
    def __init__(self, name: str, display: str):
        self.name = name
        self.display = display
        self.visuals: dict[str, dict] = {}
        self._z = 0

    def add(self, name: str, x: float, y: float, w: float, h: float, visual: dict) -> None:
        self._z += 1000
        self.visuals[name] = {
            '$schema': _VISUAL_SCHEMA,
            'name': name,
            'position': {'x': x, 'y': y, 'z': self._z, 'width': w, 'height': h, 'tabOrder': self._z},
            'visual': visual,
        }

    def page_json(self) -> dict:
        return {
            '$schema': _PAGE_SCHEMA,
            'name': self.name,
            'displayName': self.display,
            'displayOption': 'FitToPage',
            'height': _PAGE_H,
            'width': _PAGE_W,
            'objects': {
                'background': [{'properties': {
                    'color': _color('#FAFBFC'), 'transparency': _lit('0D'),
                }}],
            },
        }


def _data_visual(vtype: str, roles: dict, *, title: str | None = None, sort=None,
                  objects: dict | None = None, title_size: int = 13) -> dict:
    visual = {
        'visualType': vtype,
        'query': {'queryState': {role: {'projections': [_proj(r) for r in refs]} for role, refs in roles.items()}},
        'drillFilterOtherVisuals': True,
    }
    if sort is not None:
        visual['query']['sortDefinition'] = {
            'sort': [{'field': _field(sort[0], sort[1], sort[2]), 'direction': 'Descending'}],
            'isDefaultSort': True,
        }
    container = _panel(title, title_size=title_size)
    if container:
        visual['visualContainerObjects'] = container
    if objects:
        visual['objects'] = objects
    return visual


def _card(measure_ref, label: str) -> dict:
    visual = _data_visual('card', {'Values': [_mea(*measure_ref)]}, title=label, title_size=12)
    visual['visualContainerObjects']['title'] = _styled_title(label, 12, align='center')
    visual['objects'] = {
        'categoryLabels': [{'properties': {'show': _lit('false')}}],
        'labels': [{'properties': {
            'fontSize': _lit('28D'), 'color': _color(_IFAD_BLUE), 'fontFamily': _lit(_FONT),
            'alignment': _text_lit('center'),
        }}],
    }
    return visual


def _point_colors(entity: str, column: str, colors: dict[str, str]) -> list[dict]:
    out = []
    for value, hex_code in colors.items():
        out.append({
            'properties': {'fill': _color(hex_code)},
            'selector': {'data': [{'scopeId': {'Comparison': {
                'ComparisonKind': 0,
                'Left': _field(entity, column, 'Column'),
                'Right': {'Literal': {'Value': "'" + value.replace("'", "''") + "'"}},
            }}}]},
        })
    return out


def _line(entity: str, cat_col: str, series_col: str, y_measure: str, title: str) -> dict:
    return _data_visual(
        'lineChart',
        {'Category': [_col(entity, cat_col)], 'Series': [_col(entity, series_col)], 'Y': [_mea(entity, y_measure)]},
        title=title,
        objects={
            'lineStyles': [{'properties': {'strokeWidth': _lit('3D'), 'showMarker': _lit('true')}}],
            'categoryAxis': [{'properties': {'fontSize': _lit('9D'), 'showAxisTitle': _lit('false')}}],
            'valueAxis': [{'properties': {'fontSize': _lit('9D'), 'showAxisTitle': _lit('false')}}],
            'legend': [{'properties': {'show': _lit('true'), 'position': _text_lit('Top'), 'fontSize': _lit('9D')}}],
            'dataPoint': _point_colors(entity, series_col, LOCATION_COLORS),
        },
    )


def _table(entity: str, cols: list, title: str) -> dict:
    visual = _data_visual('tableEx', {'Values': [_col(entity, c) for c in cols]}, title=title)
    visual['objects'] = {
        'columnHeaders': [{'properties': {
            'fontSize': _lit('10D'), 'bold': _lit('true'), 'fontColor': _color('#FFFFFF'),
            'backColor': _color(_IFAD_BLUE),
        }}],
        'values': [{'properties': {'fontSize': _lit('9D')}}],
        'grid': [{'properties': {'rowPadding': _lit('4D'), 'gridVertical': _lit('false')}}],
        'stylePreset': [{'properties': {'name': _text_lit('Minimal')}}],
    }
    return visual


def _slicer(entity: str, column: str, title: str) -> dict:
    return {
        'visualType': 'slicer',
        'query': {'queryState': {'Values': {'projections': [_proj(_col(entity, column))]}}},
        'objects': {
            'data': [{'properties': {'mode': _text_lit('Dropdown')}}],
            'general': [{'properties': {'selfFilterEnabled': _lit('true')}}],
        },
        'visualContainerObjects': {
            'title': [{'properties': {
                'show': _lit('true'), 'text': _text_lit(title), 'fontFamily': _lit(_FONT),
                'fontColor': _theme_color(1, 0.2), 'bold': _lit('true'), 'fontSize': _lit('10D'),
            }}],
            'background': [{'properties': {'show': _lit('true'), 'transparency': _lit('0D')}}],
            'border': [{'properties': {'show': _lit('true'), 'color': _color('#E2E2E2'), 'radius': _lit('6D')}}],
        },
        'drillFilterOtherVisuals': True,
    }


def _textbox(paragraphs: list[tuple[str, str]]) -> dict:
    styles = {
        'h1': {'fontWeight': 'bold', 'fontSize': '18pt', 'fontFamily': 'wf_standard-font, helvetica, arial, sans-serif', 'color': _IFAD_BLUE},
        'h2': {'fontWeight': 'bold', 'fontSize': '13pt', 'color': '#5F6B6D'},
        'caption': {'fontSize': '9pt', 'color': '#5F6B6D'},
    }
    paras = [{'textRuns': [{'value': text, 'textStyle': styles[kind]}]} for kind, text in paragraphs]
    return {
        'visualType': 'textbox',
        'objects': {'general': [{'properties': {'paragraphs': paras}}]},
        'drillFilterOtherVisuals': True,
    }


def build_pages() -> list[Page]:
    overview = Page('overview', 'Overview')
    overview.add('title', 8, 10, 700, 64, _textbox([
        ('h1', 'Real-Time IoT Sensor Pipeline'),
        ('caption', 'Kafka -> Spark Structured Streaming -> Postgres -> Airflow batch rollup'),
    ]))
    overview.add('card_total', 8, 90, 200, 92, _card(('SensorReadings', 'Total Readings'), 'Total readings ingested'))
    overview.add('card_locations', 216, 90, 200, 92, _card(('SensorReadings', 'Distinct Locations'), 'Distinct locations'))
    overview.add('card_last', 424, 90, 232, 92, _card(('SensorReadings', 'Last Ingested'), 'Last ingested at (UTC)'))
    overview.add('slicer_location', 664, 90, 300, 92, _slicer('SensorWindowStats', 'location', 'Filter by location'))
    overview.add('line_temp', 8, 190, 1264, 284, _line(
        'SensorWindowStats', 'window_start', 'location', 'Avg Temperature (C)',
        'Average temperature per 1-minute window, by location'))
    overview.add('table_recent', 8, 482, 1264, 230, _table(
        'SensorReadings', ['sensor_id', 'location', 'event_time', 'temperature_c', 'humidity_pct'],
        'Latest raw readings'))

    rollup = Page('daily_rollup', 'Daily Rollup')
    rollup.add('title', 8, 10, 700, 64, _textbox([
        ('h1', 'Daily Rollup'),
        ('caption', 'Batch aggregation computed by the Airflow DAG iot_rollup_and_health'),
    ]))
    rollup.add('slicer_location', 8, 90, 300, 64, _slicer('DailyRollup', 'location', 'Filter by location'))
    rollup.add('table_rollup', 8, 162, 1264, 550, _table(
        'DailyRollup',
        ['rollup_date', 'location', 'avg_temperature_c', 'max_temperature_c', 'avg_humidity_pct', 'reading_count'],
        'Daily rollup by location'))

    return [overview, rollup]


def report_files(pages: list[Page]) -> dict[str, str]:
    files = {
        'definition.pbir': json.dumps({
            '$schema': f'{_SCHEMA}/item/report/definitionProperties/2.0.0/schema.json',
            'version': '4.0',
            'datasetReference': {'byPath': {'path': f'../{NAME}.SemanticModel'}, 'byConnection': None},
        }, indent=2),
        'definition/version.json': json.dumps({
            '$schema': f'{_SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json',
            'version': '2.0.0',
        }, indent=2),
        'definition/report.json': json.dumps({
            '$schema': f'{_SCHEMA}/item/report/definition/report/3.3.0/schema.json',
            'themeCollection': {
                'baseTheme': {
                    'name': _BASE_THEME,
                    'reportVersionAtImport': {'visual': '1.8.95', 'report': '2.0.95', 'page': '1.3.95'},
                    'type': 'SharedResources',
                },
                'customTheme': {
                    'name': _THEME_FILE,
                    'reportVersionAtImport': {'visual': '2.12.0', 'report': '3.4.0', 'page': '2.3.1'},
                    'type': 'RegisteredResources',
                },
            },
            'resourcePackages': [
                {'name': 'SharedResources', 'type': 'SharedResources',
                 'items': [{'name': _BASE_THEME, 'path': f'BaseThemes/{_BASE_THEME}.json', 'type': 'BaseTheme'}]},
                {'name': 'RegisteredResources', 'type': 'RegisteredResources',
                 'items': [
                     {'name': _THEME_FILE, 'path': _THEME_FILE, 'type': 'CustomTheme'},
                 ]},
            ],
        }, indent=2),
        'definition/pages/pages.json': json.dumps({
            '$schema': f'{_SCHEMA}/item/report/definition/pagesMetadata/1.1.0/schema.json',
            'pageOrder': [p.name for p in pages],
            'activePageName': 'overview',
        }, indent=2),
    }
    for page in pages:
        files[f'definition/pages/{page.name}/page.json'] = json.dumps(page.page_json(), indent=2, ensure_ascii=False)
        for vname, vjson in page.visuals.items():
            files[f'definition/pages/{page.name}/visuals/{vname}/visual.json'] = json.dumps(vjson, indent=2, ensure_ascii=False)
    return files


def _tmdl_name(name: str) -> str:
    if re.search(r"[\s.=:']", name):
        return "'" + name.replace("'", "''") + "'"
    return name


def _pg_source_m(pg_table: str, columns: list) -> list[str]:
    typed = ', '.join(f'{{"{name}", {dtype}}}' for name, dtype, _ in columns)
    return [
        'let',
        f'    Source = PostgreSQL.Database("{PG_SERVER}", "{PG_DATABASE}"),',
        f'    Table1 = Source{{[Schema="public",Item="{pg_table}",Kind="Table"]}}[Data],',
        f'    Typed = Table.TransformColumnTypes(Table1, {{{typed}}})',
        'in',
        '    Typed',
    ]


def _table_tmdl(table: str, pg_table: str, columns: list, measures: list) -> str:
    lines = [f'table {table}', f'\tlineageTag: {_tag()}', '']
    for name, expr, fmt in measures:
        lines += [f'\tmeasure {_tmdl_name(name)} = {expr}', f'\t\tformatString: {fmt}', f'\t\tlineageTag: {_tag()}', '']
    for name, dtype, pbi_type in columns:
        lines += [
            f'\tcolumn {name}',
            f'\t\tdataType: {pbi_type}',
            *(['\t\tformatString: 0'] if pbi_type == 'int64' else []),
            f'\t\tlineageTag: {_tag()}',
            '\t\tsummarizeBy: none',
            f'\t\tsourceColumn: {name}',
            '',
            '\t\tannotation SummarizationSetBy = Automatic',
            '',
        ]
    lines += [f'\tpartition {table} = m', '\t\tmode: import', '\t\tsource =']
    lines += [f'\t\t\t\t{ln}' for ln in _pg_source_m(pg_table, columns)]
    lines += ['', '\tannotation PBI_ResultType = Table', '']
    return '\n'.join(lines)


SENSOR_READINGS_COLS = [
    ('sensor_id', 'type text', 'string'),
    ('location', 'type text', 'string'),
    ('event_time', 'type datetime', 'dateTime'),
    ('temperature_c', 'type number', 'double'),
    ('humidity_pct', 'type number', 'double'),
    ('ingested_at', 'type datetime', 'dateTime'),
]
SENSOR_WINDOW_STATS_COLS = [
    ('location', 'type text', 'string'),
    ('window_start', 'type datetime', 'dateTime'),
    ('window_end', 'type datetime', 'dateTime'),
    ('avg_temperature_c', 'type number', 'double'),
    ('max_temperature_c', 'type number', 'double'),
    ('avg_humidity_pct', 'type number', 'double'),
    ('reading_count', 'Int64.Type', 'int64'),
]
DAILY_ROLLUP_COLS = [
    ('rollup_date', 'type date', 'dateTime'),
    ('location', 'type text', 'string'),
    ('avg_temperature_c', 'type number', 'double'),
    ('max_temperature_c', 'type number', 'double'),
    ('avg_humidity_pct', 'type number', 'double'),
    ('reading_count', 'Int64.Type', 'int64'),
    ('computed_at', 'type datetime', 'dateTime'),
]

SENSOR_READINGS_MEASURES = [
    ('Total Readings', 'COUNTROWS(SensorReadings)', '0'),
    ('Distinct Locations', 'DISTINCTCOUNT(SensorReadings[location])', '0'),
    ('Last Ingested', 'MAX(SensorReadings[ingested_at])', 'General Date'),
]
SENSOR_WINDOW_STATS_MEASURES = [
    ('Avg Temperature (C)', 'AVERAGE(SensorWindowStats[avg_temperature_c])', '0.0'),
    ('Max Temperature (C)', 'MAX(SensorWindowStats[max_temperature_c])', '0.0'),
    ('Avg Humidity (%)', 'AVERAGE(SensorWindowStats[avg_humidity_pct])', '0.0'),
]
DAILY_ROLLUP_MEASURES = [
    ('Avg Daily Temperature (C)', 'AVERAGE(DailyRollup[avg_temperature_c])', '0.0'),
]


def semantic_model_files() -> dict[str, str]:
    return {
        'definition.pbism': json.dumps({
            '$schema': f'{_SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json',
            'version': '4.2',
            'settings': {},
        }, indent=2),
        'definition/database.tmdl': 'database\n\tcompatibilityLevel: 1606\n',
        'definition/model.tmdl': (
            'model Model\n'
            '\tculture: en-US\n'
            '\tdefaultPowerBIDataSourceVersion: powerBI_V3\n'
            '\tsourceQueryCulture: en-US\n'
            '\tdataAccessOptions\n'
            '\t\tlegacyRedirects\n'
            '\t\treturnErrorValuesAsNull\n'
            '\n'
            'annotation PBI_QueryOrder = ["SensorReadings","SensorWindowStats","DailyRollup"]\n'
            '\n'
            'ref table SensorReadings\n'
            'ref table SensorWindowStats\n'
            'ref table DailyRollup\n'
        ),
        'definition/tables/SensorReadings.tmdl': _table_tmdl(
            'SensorReadings', 'sensor_readings', SENSOR_READINGS_COLS, SENSOR_READINGS_MEASURES),
        'definition/tables/SensorWindowStats.tmdl': _table_tmdl(
            'SensorWindowStats', 'sensor_window_stats', SENSOR_WINDOW_STATS_COLS, SENSOR_WINDOW_STATS_MEASURES),
        'definition/tables/DailyRollup.tmdl': _table_tmdl(
            'DailyRollup', 'daily_rollup', DAILY_ROLLUP_COLS, DAILY_ROLLUP_MEASURES),
    }


def _to_crlf_utf8(content: str) -> bytes:
    return content.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')


def main():
    pages = build_pages()
    out = OUT_DIR / NAME
    out.mkdir(parents=True, exist_ok=True)

    (out / f'{NAME}.pbip').write_bytes(_to_crlf_utf8(json.dumps({
        '$schema': f'{_SCHEMA}/pbip/pbipProperties/1.0.0/schema.json',
        'version': '1.0',
        'artifacts': [{'report': {'path': f'{NAME}.Report'}}],
        'settings': {'enableAutoRecovery': True},
    }, indent=2)))
    (out / '.gitignore').write_bytes(_to_crlf_utf8('**/.pbi/localSettings.json\n**/.pbi/cache.abf\n'))

    for rel, content in report_files(pages).items():
        path = out / f'{NAME}.Report' / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_to_crlf_utf8(content))

    report_dir = out / f'{NAME}.Report'
    (report_dir / 'StaticResources/SharedResources/BaseThemes').mkdir(parents=True, exist_ok=True)
    (report_dir / 'StaticResources/SharedResources/BaseThemes' / f'{_BASE_THEME}.json').write_bytes(
        (_ASSETS / f'{_BASE_THEME}.json').read_bytes())
    (report_dir / 'StaticResources/RegisteredResources').mkdir(parents=True, exist_ok=True)
    (report_dir / 'StaticResources/RegisteredResources' / _THEME_FILE).write_bytes(
        (_ASSETS / _THEME_FILE).read_bytes())

    for rel, content in semantic_model_files().items():
        path = out / f'{NAME}.SemanticModel' / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_to_crlf_utf8(content))

    print(f'Wrote PBIP project to {out}')


if __name__ == '__main__':
    main()
