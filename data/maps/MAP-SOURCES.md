# Steppe Jukebox: контуры областей

## Подготовка новых областей (issue #23)

- Северо-Казахстанская область: `north-kazakhstan.geojson`, [OpenStreetMap relation 215760](https://www.openstreetmap.org/relation/215760).
- Павлодарская область: `pavlodar.geojson`, [OpenStreetMap relation 215772](https://www.openstreetmap.org/relation/215772).

Геометрии WGS 84 получены 16.11.2026 через поиск Nominatim с `polygon_geojson=1`; сохранены все полигоны и внутренние кольца. Источник: [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright), лицензия [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Сетка и маршруты используют эту же геометрию.

## Костанайская область · `kostanay-oblast.svg`

- Непосредственный источник: экран `spring` из `Steppe-Jukebox-Preview-Akmola.html`.
- Тот же векторный контур, с полностью совпадающим путём SVG, найден в `screens/spring.svg` исходного `Steppe-Jukebox-Figma-Package.zip`. README этого пакета указывает географическую основу: проектный GeoJSON из [OpenStreetMap, relation 1288730](https://www.openstreetmap.org/relation/1288730), KZ-39, данные на 11.11.2026 по README.
- Атрибуция: [© OpenStreetMap contributors, ODbL](https://www.openstreetmap.org/copyright). Для публичного интерфейса покажите атрибуцию рядом с картой.
- Какой исходный векторный PDF использовали на других этапах и связан ли он с этим конкретным контуром, не подтверждено.

## Акмолинская область · `akmola-oblast.svg`

- Новый контур заменяет контур из HTML-прототипа. Источник: [OpenStreetMap, relation 215743](https://www.openstreetmap.org/relation/215743), Ақмола облысы / Акмолинская область, административный уровень 4, Wikidata Q485056.
- Геометрия получена 14.11.2026 через [OSM Nominatim — экспорт объекта R215743](https://nominatim.openstreetmap.org/lookup?osm_ids=R215743&format=jsonv2&polygon_geojson=1&extratags=1). Приложен `akmola-oblast.geojson` с координатами WGS 84 в порядке долгота, широта. Сохранены внешний контур и пять внутренних колец; внутренних колец на карте не закрашивать.
- SVG построен без упрощения геометрии. Для визуального представления: `x = 8 + (lon - 65.3524166) * 100 * cos(52°)`, `y = 8 + (53.6843697 - lat) * 100`. Это преобразование для отрисовки, не сетка в километрах. При наложении существующего маршрута перепроецируйте его по известным координатам, не переносите старые экранные пиксели.
- Атрибуция: [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright); геоданные под [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Для публичного интерфейса покажите атрибуцию рядом с картой.

## Подключение

Оба SVG имеют прозрачный фон; демонстрационные квадраты, маршруты, подписи и звук не перенесены. Костанайский SVG сохранён из предыдущего пакета; Акмолинский перестроен из геоданных. У SVG разные `viewBox`; экранные координаты не являются широтой и долготой.

Для [задачи #3](https://github.com/DAIRN-Universe/steppe-jukebox/issues/3) их можно использовать как визуальные основы. Чтобы наложить координатную сетку, используйте WGS 84 GeoJSON для Акмолинской области, а Костанайскую основу привяжите по её исходной геометрии; затем рисуйте данные и подсветку отдельным слоем по `cell_id`. Датированные ряды NASA относятся к данным маршрута, а не к контурам областей.

- Западно-Казахстанская область: `west-kazakhstan.geojson`, [OSM relation 215441](https://www.openstreetmap.org/relation/215441).
- Актюбинская область: `aktobe.geojson`, [OSM relation 215683](https://www.openstreetmap.org/relation/215683).
- Карагандинская область: `karaganda.geojson`, [OSM relation 215776](https://www.openstreetmap.org/relation/215776).
- Область Абай: `abai.geojson`, [OSM relation 14243026](https://www.openstreetmap.org/relation/14243026).

Геометрии WGS 84 получены 16.11.2026 из Nominatim (`polygon_geojson=1`), включая внутренние кольца; атрибуция и условия ODbL указаны выше. Сетка строится непосредственно из той же геометрии; точки маршрутов привязаны к центрам целиком внутренних ячеек, а именованные населённые пункты служат приблизительными ориентирами.
