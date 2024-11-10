# yandex-music-downloader

> Внимание! В версии v3 был изменен способ авторизации и некоторые
> аргументы. Смотрите [MIGRATION.md](MIGRATION.md) для получения информации
> об изменениях

## Содержание
1. [О программе](#О-программе)
2. [Установка](#Установка)
3. [Получение данных для авторизации](#Получение-данных-для-авторизации)
4. [Примеры использования](#Примеры-использования)
5. [Спасибо](#Спасибо)
6. [Использование](#Использование)
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
    - Дата выпуска альбома
    - Обложка альбома
    - Название альбома
    - Текст песни (при использовании флага `--add-lyrics`)
- Поддержка паттерна для пути сохранения музыки

## Установка
Для запуска скрипта требуется Python 3.9+
```
pip install git+https://github.com/llistochek/yandex-music-downloader
yandex-music-downloader --help
```

## Получение данных для авторизации
https://yandex-music.readthedocs.io/en/main/token.html

## Примеры использования
Во всех примерах замените `<Токен>` на ваш токен.

### Скачать все треки [Twenty One Pilots](https://music.yandex.ru/artist/792433) в высоком качестве
```
yandex-music-downloader --token "<Токен>" --quality 1 --url "https://music.yandex.ru/artist/792433"
```

### Скачать альбом [Nevermind](https://music.yandex.ru/album/294912) в высоком качестве, загружая тексты песен
```
yandex-music-downloader --token "<Токен>" --quality 1 --add-lyrics --url "https://music.yandex.ru/album/294912"
```

### Скачать трек [Seven Nation Army](https://music.yandex.ru/album/11644078/track/6705392)
```
yandex-music-downloader --token "<Токен>" --url "https://music.yandex.ru/album/11644078/track/6705392"
```

## Использование
```
usage: yandex-music-downloader [-h] [--quality <Качество>] [--skip-existing]
                               [--add-lyrics] [--embed-cover]
                               [--cover-resolution <Разрешение обложки>]
                               [--delay <Задержка>] [--stick-to-artist]
                               [--only-music]
                               (--artist-id <ID исполнителя> | --album-id <ID альбома> | --track-id <ID трека> | --playlist-id <владелец плейлиста>/<тип плейлиста> | -u URL)
                               [--unsafe-path] [--dir <Папка>]
                               [--path-pattern <Паттерн>] --token <Токен>

Загрузчик музыки с сервиса Яндекс.Музыка

options:
  -h, --help            show this help message and exit

Общие параметры:
  --quality <Качество>  Качество трека:
                        0 - Низкое (mp3 128kbps)
                        1 - Высокое (mp3 320kbps)
                        (по умолчанию: 0)
  --skip-existing       Пропускать уже загруженные треки
  --add-lyrics          Загружать тексты песен
  --embed-cover         Встраивать обложку в .mp3 файл
  --cover-resolution <Разрешение обложки>
                        по умолчанию: 400
  --delay <Задержка>    Задержка между запросами, в секундах (по умолчанию: 0)
  --stick-to-artist     Загружать альбомы, созданные только данным исполнителем
  --only-music          Загружать только музыкальные альбомы (пропускать подкасты и аудиокниги)

ID:
  --artist-id <ID исполнителя>
  --album-id <ID альбома>
  --track-id <ID трека>
  --playlist-id <владелец плейлиста>/<тип плейлиста>
  -u URL, --url URL     URL исполнителя/альбома/трека/плейлиста

Указание пути:
  --unsafe-path         Не очищать путь от недопустимых символов
  --dir <Папка>         Папка для загрузки музыки (по умолчанию: .)
  --path-pattern <Паттерн>
                        Поддерживает следующие заполнители: #number, #artist, #album-artist, #title, #album, #year, #artist-id, #album-id, #track-id, #number-padded (по умолчанию: #album-artist/#album/#number - #title)

Авторизация:
  --token <Токен>       Токен для авторизации. См. README для способов получения
```

## Спасибо
Разработчикам проекта [yandex-music-api](https://github.com/MarshalX/yandex-music-api)

## Дисклеймер
Данный проект является независимой разработкой и никак не связан с компанией Яндекс.
