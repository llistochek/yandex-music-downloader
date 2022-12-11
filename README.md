# yandex-music-downloader

## Содержание
1. [О программе](#О-программе)
2. [Установка](#Установка)
3. [Получение данных для авторизации](#Получение-данных-для-авторизации)
4. [Примеры использования](#Примеры-использования)
5. [Использование](#Использование)
6. [Спасибо](#Спасибо)
7. [Дисклеймер](#Дисклеймер)


## О программе
Загрузчик, созданный вследствие наличия *фатального недостатка* в проекте [yandex-music-download](https://github.com/kaimi-io/yandex-music-download).

### Возможности
- Возможность загрузки:
    - Всех треков исполнителя
    - Всех треков из альбома
    - Всех треков из плейлиста
    - Отдельного трека
- Загрузка всех метаданных трека/альбома:
    - Номер трека
    - Номер диска
    - Название трека
    - Исполнитель
    - Дополнительные исполнители
    - Год выпуска альбома
    - Обложка альбома
    - Название альбома
    - Текст песни (при использовании флага `--add-lyrics`)
- Поддержка паттерна для пути сохранения музыки

## Установка
Для запуска скрипта требуется Python 3.8+
```
git clone https://github.com/llistochek/yandex-music-downloader.git
cd yandex-music-download
pip install -r requirements.txt
python3 main.py
```

## Получение данных для авторизации
Войдите в свой Яндекс аккаунт, затем проделайте следующие шаги:

### Для Google Chrome/Chromium
1. Перейдите на сайт Яндекс Музыки (https://music.yandex.ru) 
2. Нажмите F12
3. Выберите вкладку Application
4. Выберите пункт Cookies->https://music.yandex.ru
5. Скопируйте значение куки (кликните на значение куки 2 раза -> Ctrl+C):
    - Куки `Session_id` - это аргумент `--sesion-id`


### Для Firefox
1. Перейдите на сайт Яндекс Музыки (https://music.yandex.ru) 
2. Нажмите F12
3. Выберите вкладку Storage
4. Выберите пункт Куки->https://music.yandex.ru
5. Скопируйте значение куки (кликните на значение куки 2 раза -> Ctrl+C):
    - Куки `Session_id` - это аргумент `--sesion-id`


## Примеры использования
Во всех примерах замените `<ID сессии>` на значение куки `Session_id`

### Скачать все треки [Twenty One Pilots](https://music.yandex.ru/artist/792433) в высоком качестве
```
python3 main.py --session-id "<ID Сессии>" --hq --url "https://music.yandex.ru/artist/792433"
```

### Скачать альбом [Nevermind](https://music.yandex.ru/album/294912) в высоком качестве, загружая тексты песен
```
python3 main.py --session-id "<ID Сессии>" --hq --add-lyrics --url "https://music.yandex.ru/album/294912"
```

### Скачать трек [Seven Nation Army](https://music.yandex.ru/album/11644078/track/6705392)
```
python3 main.py --session-id "<ID Сессии>" --url "https://music.yandex.ru/album/11644078/track/6705392"
```

## Использование

```
usage: main.py [-h] [--hq] [--skip-existing]
               [--cover-resolution <Разрешение обложки>] [--add-lyrics]
               [--delay <Задержка>] [--add-version] [--stick-to-artist]
               [--log-level {CRITICAL,FATAL,ERROR,WARN,WARNING,INFO,DEBUG,NOTSET,VERBOSE}]
               (--artist-id <ID исполнителя> | --album-id <ID альбома> | --track-id <ID трека> | --playlist-id <владелец плейлиста>/<тип плейлиста> | -u URL)
               [--strict-path] [--dir <Папка>] [--path-pattern <Паттерн>]
               --session-id <ID сессии> [--user-agent <User-Agent>]

Загрузчик музыки с сервиса Яндекс.Музыка

optional arguments:
  -h, --help            show this help message and exit

Общие параметры:
  --hq                  Загружать треки в высоком качестве (по умолчанию:
                        False)
  --skip-existing       Пропускать уже загруженные треки (по умолчанию: False)
  --cover-resolution <Разрешение обложки>
                        (по умолчанию: 400)
  --add-lyrics          Загружать тексты песен (по умолчанию: False)
  --delay <Задержка>    Задержка между запросами, в секундах (по умолчанию: 3)
  --add-version         Добавлять информацию о версии трека (по умолчанию:
                        False)
  --stick-to-artist     Загружать только альбомы созданные данным исполнителем
                        (по умолчанию: False)
  --log-level {CRITICAL,FATAL,ERROR,WARN,WARNING,INFO,DEBUG,NOTSET,VERBOSE}

ID:
  --artist-id <ID исполнителя>
  --album-id <ID альбома>
  --track-id <ID трека>
  --playlist-id <владелец плейлиста>/<тип плейлиста>
  -u URL, --url URL     URL исполнителя/альбома/трека/плейлиста

Указание пути:
  --strict-path         Очищать путь от недопустимых символов (по умолчанию:
                        False)
  --dir <Папка>         Папка для загрузки музыки (по умолчанию: .)
  --path-pattern <Паттерн>
                        Поддерживает следующие заполнители: #number, #artist,
                        #album-artist, #title, #album, #year (по умолчанию:
                        #album-artist/#album/#number - #title)

Авторизация:
  --session-id <ID сессии>
  --user-agent <User-Agent>
                        по умолчанию: Mozilla/5.0 (X11; Linux x86_64)
                        AppleWebKit/537.36 (KHTML, like Gecko)
                        Chrome/106.0.0.0 Safari/537.36
```

## Спасибо
Разработчикам проекта [yandex-music-download](https://github.com/kaimi-io/yandex-music-download). Оттуда был взят [код хэширования](https://github.com/kaimi-io/yandex-music-download/blob/808443cb32be82e1f54b2f708884cb7c941b4371/src/ya.pl#L720).

## Дисклеймер
Данный проект является независимой разработкой и никак не связан с компанией Яндекс.
