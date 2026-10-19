# Статус

Обновлено: 2026-10-19 09:45:27 UTC.

Ниже пункты `docs/TASK.md`. Доказательство — имя теста или записанная ручная проверка. Выдуманных прогонов нет.

## Работает

Профиль: почта и номера машин. Регистрация, вход, `GET /api/me/`, добавление номера. Тесты `test_register_normalizes_email_and_rejects_duplicates_and_weak_passwords`, `test_me_and_vehicles_require_a_token_and_normalize_the_plate`, `test_duplicate_plate_is_409_and_does_not_name_the_owner`. На экране есть вкладки «Вход», «Профиль» и кнопка «Добавить машину». 2026-10-18 одна вкладка: вход `demo@example.com` открыл профиль с почтой и `A000AA`.

Схема: места `P01`–`P12`, состояния «свободно», «забронировано», «занято». Занятое важнее забронированного. «Забронировано» — не весь интервал, а окно `starts_at - 15 минут <= сейчас < starts_at + 15 минут`. Тест `test_spot_statuses_follow_the_hold_window`. Список публичный: `test_spots_are_public_and_one_query_covers_every_spot`.

Бронь: интервал и машина водителя, от 15 минут до 24 часов. Тесты `test_duration_boundaries_and_touching_intervals`, `test_bookings_require_a_token_and_reject_bad_input`. На экране вкладка «Мои брони».

Шлагбаум: заезд и выезд по номеру, без токена. Тесты `test_gate_is_public_and_reports_entry_conflicts`, `test_exit_bills_the_stay_and_completes_the_booking`. На экране вкладка «Шлагбаум», кнопки «Заезд» и «Выезд». 2026-10-18 заезд в одной вкладке вернул место и время.

Тариф и счёт. Строка тарифа с 2020-01-01: `Asia/Bishkek`, день 07:00–23:00 по 200 копеек, ночь по 100. Считаются начатые минуты, сумма — целое число копеек. Граница дня и ночи, полночь, смена тарифа, нулевая длительность и поминутный эталон: `test_day_into_night_at_23`, `test_night_into_day_at_07`, `test_across_midnight_stays_night`, `test_tariff_change_splits_the_visit`, `test_zero_duration_is_free`, `test_partial_minutes_round_up_and_an_exact_minute_does_not`, `test_matches_a_per_minute_reference`. Счёт пишется при выезде: `test_driver_books_enters_exits_and_reads_one_invoice`.

История визитов и счетов. Тот же сквозной тест и `test_history_requires_a_token`. На экране вкладка «История»: номер, место, заезд, выезд и сумма, если счёт уже есть.

Две брони одного места не пересекаются, в том числе при одновременной записи. Ограничение PostgreSQL и тест `test_parallel_bookings_of_one_spot_allow_a_single_winner`.

Незаезженная бронь снимается через 15 минут после начала. Тесты `test_expire_uses_the_entry_window_and_leaves_other_statuses`, `test_expire_task_releases_overdue_bookings_and_is_idempotent`.

Одно письмо в последние 10 минут брони. Тесты `test_a_booking_in_the_window_gets_one_email`, `test_window_boundaries`, `test_parallel_sends_leave_one_email_per_booking`. В Compose почта уходит в Mailpit.

Заезд без брони берёт свободное место с наименьшим pk, счёт — по фактической стоянке. Нет места — ошибка, визит не создаётся. Тесты `test_walk_in_picks_the_lowest_spot_pk`, `test_no_free_place_leaves_the_booking_active`, `test_exit_bills_the_stay_and_completes_the_booking`.

Выезд без заезда и второй заезд по тому же номеру учёт не ломают. Тесты `test_exit_without_entry_creates_nothing`, `test_double_entry_unknown_plate_and_plate_spellings`, `test_parallel_entries_of_one_plate_leave_one_visit`.

`docker compose up --build` после миграций вызывает `seed_demo`. Повтор ничего не дублирует: `test_seed_demo_can_run_twice`.

Занятость меняется во второй вкладке без перезагрузки. Сервер: `test_two_clients_both_receive_the_signal`. Клиент перечитывает список по сигналу, при обрыве опрашивает раз в 5 секунд: тесты `useSpots`. 2026-10-19 две вкладки http://localhost:8080. Первая осталась на «Схеме»: «Связь: онлайн», `P01`–`P12` свободно. Вторая — «Шлагбаум», номер `C777CC`, «Заезд»: «Место P01. Заезд 10/19/2026, 3:44:36 PM.». Первая без перезагрузки показала `P01` «занято». «Выезд»: «Выезд 10/19/2026, 3:44:50 PM. Итого 2.00.». Первая снова показала `P01` «свободно». Итог виден на шлагбауме, не на схеме.

2026-10-19 с чистого клона: `docker compose run --rm backend pytest` — 84 passed; `docker compose run --rm --no-deps frontend npm test` — 16 passed.

## Работает частично

Письмо и снятие брони делает Celery раз в 60 секунд (`test_both_jobs_run_every_minute`). Срабатывание может отстать от границы до минуты. Пропущенное окно письма задним числом не отправляется: `test_a_missed_window_is_not_sent_later`. 2026-10-19 на живом стенде beat слал `send-due-reminders` каждую минуту, worker отвечал «Sent 0», пока до конца брони было больше 10 минут. Mailpit в этот момент был пуст. Доставку письма в ящик глазами не смотрели.

## Не делали и почему

Закрепить версии в `backend/requirements/base.txt`, кроме `pytest-django==4.14.0`. Так решено в журнале 2026-10-17 19:11:18 UTC, чтобы не фиксировать пакеты до проверки.

Монтировать код хоста в контейнер API. Образ копирует исходники при сборке. Уже запущенный контейнер видит правку после пересборки.

Удаление машины на экране. В журнале 2026-10-18 08:19:05 UTC: на экране его нет. API удаления есть и отвечает `409`, пока строку держит `PROTECT`, в том числе после отменённой или завершённой брони: `test_finished_booking_still_blocks_delete_because_the_row_is_protected`.

Экспорт сессии агента в репозиторий не клали. Задание принимает журнал решений вместо него. Журнал — `DECISIONS.md`, время в коммитах есть.

## Компромиссы

Пересадка. Если забронированное место занято, визит создаётся на другом, а `booking.spot` не меняется. Бронь остаётся `checked_in` и до `ends_at` не пускает на это место новую бронь. На схеме исходное место при этом «свободно»: цвет смотрит только статус `active`. Журнал 2026-10-17 19:11:18 UTC, тест `test_taken_booking_spot_assigns_another_and_keeps_the_original`.

Письмо при сбое отправки не повторяется. `sent_at` записывается до `send_mail`. Упавший SMTP оставляет отметку, второй попытки нет: так не возникает второго письма. Тест `test_a_failed_delivery_is_not_retried_and_does_not_stop_the_rest`. Журнал 2026-10-17 21:28:27 UTC.

Опоздание письма и снятия — до минуты. Обе задачи в beat раз в 60 секунд. Журнал называет эту задержку допустимой.

Сигнал схемы раз в 15 секунд. Наступление начала брони и конец окна заезда ничего не пишут в базу, а цвет места меняется. Периодический сигнал заставляет открытые клиенты перечитать список. Журнал 2026-10-18 06:40:13 UTC, тест `test_periodic_notify_sends_and_is_scheduled_every_fifteen_seconds`.
