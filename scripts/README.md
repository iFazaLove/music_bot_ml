# Одноразовые команды

В этой папке находятся небольшие служебные команды, которые запускаются вручную и не
участвуют в обычной работе бота.

## Загрузка анимированного аватара

Перед запуском проверь, что в `.env` указан `MUSIC_BOT_TOKEN`. Команда сразу заменяет
текущий аватар бота:

```bash
python scripts/set_bot_avatar.py
```

По умолчанию используется файл
`assets/branding/music-bot-avatar-animated.mp4`. Можно передать другой путь:

```bash
python scripts/set_bot_avatar.py path/to/avatar.mp4
```

Кадр для статичного превью выбирается временем в секундах:

```bash
python scripts/set_bot_avatar.py --main-frame-timestamp 0.5
```

Скрипт использует IPv4-соединение с Telegram. Это помогает при работе через VPN или
DNS-прокси, которые возвращают IPv4-mapped IPv6-адрес и вызывают ошибку `aiohttp`.
