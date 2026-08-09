# ledgermind-integrations

`ledgermind-integrations` — открытый client-side слой LedgerMind для
захвата RawRound. Он не является Local и не содержит закрытый Core.

## Capture-only runtime

- Интеграции наблюдают только данные, доступные в клиенте, и собирают один
  неизменяемый завершённый `RawRound` с `schema_version=2`: сообщения, tool calls/results,
  границы раунда и provenance.
- Они не извлекают semantic fields, не создают Hypothesis/Atom и не принимают
  решения о knowledge.
- Интеграции **не вызывают модели** и не содержат model provider, inference
  profile или provider secret. Модельная обработка выполняется Local или
  выбранной облачной службой после приёма RawRound.

## Delivery endpoint

После валидации и canonical digest интеграция может доставить RawRound через
публичный protocol на выбранный пользователем endpoint:

- локальный Local endpoint, обычно `POST /rounds`;
- выбранный пользователем Cloud endpoint с тем же public contract.

Адрес, authentication и egress policy задаются владельцем установки. Поэтому
доставка может передать наблюдаемый conversation/tool payload за пределы
машины; Integrations не скрывает этот boundary и не отправляет semantic
hypotheses или credentials.

## Durable spool sensitivity

Spool нужен для bounded retry и восстановления после перезапуска. Его записи
могут содержать raw conversation, tool arguments/results, source identity и
provenance — это чувствительные данные, даже если provider secret из них
удалён.

Держите spool в каталоге с private permissions, ограничивайте размер и срок
хранения, не синхронизируйте его в публичные каталоги и не коммитьте в Git.
Архивы и quarantine records обрабатывайте как чувствительные backup artifacts;
передавайте их только по доверенному каналу.

## Hermes plugin package

Установка регистрирует plugin entrypoint и поставляет `plugin.yaml`:

```bash
ledgermind-integrations install hermes --destination ~/.hermes/plugins
```

Регистрация выполняется через публичный Hermes hook surface. Hooks только
захватывают наблюдаемые события, fail open на транспортной ошибке и не делают
модельные вызовы или неограниченные retry-loop внутри callback.

## Package boundary

Wheel Integrations должен содержать только namespaced
`ledgermind_integrations` runtime, Hermes plugin entry и bundled
`adapters/hermes/plugin.yaml`; build-копии, test DB, `.pyc`, private keys и
секретные env-файлы в release contents не входят. Общий `ledgermind-protocol`
поставляет `py.typed`, RawRound schema, canonical JSON и conformance fixtures.
