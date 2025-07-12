from enum import Enum


class HelpPanels(str, Enum):
    '''
    Панели справки для CLI опций (отображаются в справке как группы - удобно)
    '''


    auth = "Авторизация"
    network = "Сеть"
    download = "Параметры загрузки"
    file_managing = "Управление файлами"
    metadata = "Метаданные треков"
