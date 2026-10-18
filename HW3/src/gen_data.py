"""
Генератор синтетического датасета IT-вакансий, написан Клодом и вроде детерминированный
Запуск (из корня HW3): python src/gen_data.py --rows 250000
"""
import argparse
import csv
import random

from collections import namedtuple
from datetime import date, timedelta
from pathlib import Path

import numpy as np


CPP_ROLE = "Программист, разработчик на C и C++"

# Профиль вакансии: доля среди C/C++ вакансий, множитель зарплаты, вероятность каждого навыка
Profile = namedtuple("Profile", ["share", "salary_multiplier", "skill_probabilities"])

# Регион: вес среди вакансий, множитель зарплаты, поправки к долям профилей
Area = namedtuple("Area", ["weight", "salary_multiplier", "profile_multipliers"])

OTHER_ROLES = {
    "Программист, разработчик на Python": [
        "Python", "Django", "FastAPI", "PostgreSQL", "Docker", "Git", "Linux", "SQL", "REST API", "Redis", "Celery",
        "pytest",
    ],
    "Программист, разработчик на Java": [
        "Java", "Spring", "Hibernate", "PostgreSQL", "Kafka", "Docker", "Git", "SQL", "Maven", "REST API",
        "Microservices",
    ],
    "Программист, разработчик на Go": [
        "Go", "gRPC", "Docker", "Kubernetes", "PostgreSQL", "Kafka", "Git", "Linux", "Redis", "Microservices",
    ],
    "Программист 1С": [
        "1C", "1С: Управление торговлей", "1С: Бухгалтерия", "SQL", "Запросы 1С", "Обмен данными", "ERP", "Git",
    ],
    "Фронтенд-разработчик": [
        "JavaScript", "TypeScript", "React", "Vue.js", "HTML", "CSS", "Git", "Webpack", "Redux", "REST API",
        "Node.js",
    ],
    "Аналитик": [
        "SQL", "Excel", "Python", "Power BI", "BPMN", "UML", "Jira", "Confluence", "Аналитика данных", "Tableau",
    ],
    "DevOps-инженер": [
        "Docker", "Kubernetes", "Linux", "Git", "CI/CD", "Ansible", "Terraform", "Bash", "Prometheus", "Grafana",
        "Python",
    ],
    "Программист, разработчик на PHP": [
        "PHP", "Laravel", "MySQL", "Git", "Linux", "JavaScript", "Symfony", "Redis", "REST API", "Docker",
    ],
    "Мобильный разработчик": [
        "Kotlin", "Swift", "Android", "iOS", "Git", "REST API", "Flutter", "Firebase", "SQL",
    ],
    "Тестировщик (QA)": [
        "Python", "SQL", "Postman", "Selenium", "Jira", "Git", "pytest", "Тестирование API", "Linux",
    ],
}
OTHER_ROLE_WEIGHTS = [0.17, 0.15, 0.07, 0.10, 0.16, 0.10, 0.07, 0.07, 0.06, 0.05]

# Навыки из чужих сегментов, которые иногда попадают и в C/C++ вакансии
FOREIGN_SKILLS_IN_OTHER_ROLES = ["C++", "Linux", "Git", "CMake", "C"]

# Каноническое название навыка -> написания, которые встречаются в вакансиях
SKILL_SPELLINGS = {
    "C++": ["C++", "c++", "С++", "Си++", "C/C++"],  # в третьем написании кириллическая «С»
    "C": ["C", "c", "Си", "С"],
    "C++17": ["C++17", "c++17"],
    "C++20": ["C++20", "c++20"],
    "STL": ["STL", "stl"],
    "Boost": ["Boost", "boost", "Boost C++"],
    "Qt": ["Qt", "qt", "QT", "Qt5"],
    "QML": ["QML", "qml"],
    "CMake": ["CMake", "cmake", "Cmake"],
    "Make": ["Make", "make", "Makefile"],
    "Linux": ["Linux", "linux", "Линукс", "GNU/Linux"],
    "Git": ["Git", "git", "GIT"],
    "SVN": ["SVN", "svn", "Subversion"],
    "Python": ["Python", "python", "Питон"],
    "Многопоточность": ["Многопоточность", "Multithreading", "multithreading", "Многопоточное программирование"],
    "TCP/IP": ["TCP/IP", "tcp/ip", "TCP IP", "Сетевые протоколы"],
    "Embedded": ["Embedded", "embedded", "Встраиваемые системы"],
    "RTOS": ["RTOS", "rtos", "FreeRTOS"],
    "Embedded Linux": ["Embedded Linux", "embedded linux", "Yocto"],
    "Микроконтроллеры": ["Микроконтроллеры", "микроконтроллеры", "MCU"],
    "STM32": ["STM32", "stm32"],
    "ARM": ["ARM", "arm"],
    "SPI/I2C/UART": ["SPI/I2C/UART", "UART", "I2C", "SPI"],
    "CAN": ["CAN", "CAN bus"],
    "Modbus": ["Modbus", "modbus"],
    "MQTT": ["MQTT", "mqtt"],
    "Схемотехника": ["Схемотехника", "схемотехника", "Чтение схем"],
    "FPGA": ["FPGA", "fpga", "ПЛИС"],
    "Verilog": ["Verilog", "verilog", "VHDL"],
    "Assembler": ["Assembler", "assembler", "Ассемблер", "asm"],
    "Драйверы": ["Драйверы", "Drivers", "Разработка драйверов"],
    "Linux kernel": ["Linux kernel", "Linux Kernel", "Ядро Linux"],
    "SQL": ["SQL", "sql"],
    "PostgreSQL": ["PostgreSQL", "postgresql", "Postgres"],
    "Docker": ["Docker", "docker"],
    "CI/CD": ["CI/CD", "ci/cd", "CI CD"],
    "Jenkins": ["Jenkins", "jenkins"],
    "Kafka": ["Kafka", "kafka"],
    "Redis": ["Redis", "redis"],
    "gRPC": ["gRPC", "grpc"],
    "Protobuf": ["Protobuf", "protobuf", "Protocol Buffers"],
    "Bash": ["Bash", "bash", "Shell"],
    "Lua": ["Lua", "lua"],
    "Rust": ["Rust", "rust"],
    "CUDA": ["CUDA", "cuda"],
    "OpenCV": ["OpenCV", "opencv"],
    "Компьютерное зрение": ["Компьютерное зрение", "Computer vision", "CV"],
    "ROS": ["ROS", "ros", "ROS2"],
    "OpenMP": ["OpenMP", "openmp"],
    "SIMD": ["SIMD", "simd", "AVX"],
    "Linear algebra": ["Linear algebra", "Линейная алгебра"],
    "Математика": ["Математика", "математика", "Численные методы"],
    "OpenGL": ["OpenGL", "opengl"],
    "Vulkan": ["Vulkan", "vulkan"],
    "DirectX": ["DirectX", "directx"],
    "Unreal Engine": ["Unreal Engine", "unreal engine", "UE4", "UE5"],
    "Unity": ["Unity", "unity"],
    "C#": ["C#", "c#", "С#"],
    "Java": ["Java", "java"],
    "Windows": ["Windows", "windows"],
    "WinAPI": ["WinAPI", "winapi", "Win32"],
    "MFC": ["MFC", "mfc"],
    "Delphi": ["Delphi", "delphi"],
    "Pascal": ["Pascal", "pascal", "Паскаль"],
    "Access": ["Access", "MS Access"],
    "Visual Studio": ["Visual Studio", "visual studio", "MSVC"],
    "ООП": ["ООП", "OOP", "Объектно-ориентированное программирование"],
    "Паттерны проектирования": ["Паттерны проектирования", "Design patterns", "design patterns"],
    "Алгоритмы и структуры данных": [
        "Алгоритмы и структуры данных", "Алгоритмы", "Algorithms", "Data structures",
    ],
    "GDB": ["GDB", "gdb"],
    "Valgrind": ["Valgrind", "valgrind"],
    "GCC": ["GCC", "gcc", "g++"],
    "Clang": ["Clang", "clang", "LLVM"],
    "Google Test": ["Google Test", "GoogleTest", "gtest"],
    "Unit-тестирование": ["Unit-тестирование", "Unit testing", "Юнит-тесты"],
    "Low latency": ["Low latency", "low latency", "Низкие задержки"],
    "FIX protocol": ["FIX protocol", "FIX"],
    "Алготрейдинг": ["Алготрейдинг", "алготрейдинг", "HFT"],
    "Kubernetes": ["Kubernetes", "k8s"],
    "Perforce": ["Perforce", "perforce"],
    "Wireshark": ["Wireshark", "wireshark"],
    "REST API": ["REST API", "REST", "rest api"],
    "Asio": ["Asio", "asio", "Boost.Asio"],
    "Технический английский": ["Технический английский", "Английский язык", "English"],
    "Agile": ["Agile", "Scrum", "agile"],
}

# Навыки, которых нет в словаре синонимов (после нормализации остаются «как есть» в нижнем регистре)
RARE_SKILLS = [
    "Conan", "vcpkg", "Bazel", "Meson", "FlatBuffers", "SObjectizer", "AddressSanitizer", "Catch2", "ZeroMQ",
    "libuv", "Doxygen", "Ninja",
]

# Множитель к зарплате от отдельных навыков
SKILL_SALARY_EFFECT = {
    "Low latency": 1.25,
    "CUDA": 1.12,
    "Linux kernel": 1.10,
    "Rust": 1.12,
    "Vulkan": 1.08,
    "Kafka": 1.06,
    "SIMD": 1.10,
    "Kubernetes": 1.08,
    "gRPC": 1.05,
    "Алготрейдинг": 1.10,
    "MFC": 0.90,
    "Delphi": 0.88,
    "Pascal": 0.86,
    "SVN": 0.95,
    "Access": 0.88,
    "Visual Studio": 0.96,
    "ООП": 0.97,
    "Алгоритмы и структуры данных": 0.98,
}

PROFILES = {
    "embedded": Profile(0.22, 0.95, {
        "C": 0.85,
        "C++": 0.55,
        "Embedded": 0.6,
        "STM32": 0.35,
        "RTOS": 0.35,
        "ARM": 0.35,
        "SPI/I2C/UART": 0.3,
        "Микроконтроллеры": 0.4,
        "Linux": 0.45,
        "Git": 0.6,
        "GDB": 0.25,
        "CAN": 0.2,
        "Modbus": 0.12,
        "Embedded Linux": 0.2,
        "Assembler": 0.2,
        "Схемотехника": 0.15,
        "FPGA": 0.08,
        "Verilog": 0.06,
        "Драйверы": 0.15,
        "Linux kernel": 0.08,
        "MQTT": 0.08,
        "Python": 0.15,
        "CMake": 0.2,
        "Make": 0.2,
    }),
    "backend": Profile(0.20, 1.15, {
        "C++": 0.97,
        "Linux": 0.8,
        "Многопоточность": 0.6,
        "TCP/IP": 0.5,
        "Boost": 0.4,
        "STL": 0.5,
        "Docker": 0.35,
        "PostgreSQL": 0.3,
        "gRPC": 0.15,
        "Protobuf": 0.15,
        "Redis": 0.12,
        "Kafka": 0.1,
        "Python": 0.3,
        "Git": 0.7,
        "CMake": 0.45,
        "CI/CD": 0.2,
        "Jenkins": 0.1,
        "Алгоритмы и структуры данных": 0.25,
        "Паттерны проектирования": 0.2,
        "C++17": 0.25,
        "C++20": 0.12,
        "Google Test": 0.2,
        "Asio": 0.1,
        "SQL": 0.25,
        "Bash": 0.15,
        "Rust": 0.02,
        "Kubernetes": 0.06,
        "Wireshark": 0.05,
    }),
    "desktop": Profile(0.15, 0.95, {
        "C++": 0.97,
        "Qt": 0.8,
        "QML": 0.3,
        "STL": 0.5,
        "Windows": 0.45,
        "WinAPI": 0.2,
        "CMake": 0.35,
        "Git": 0.7,
        "ООП": 0.3,
        "Паттерны проектирования": 0.25,
        "OpenGL": 0.1,
        "C#": 0.1,
        "Python": 0.15,
        "Linux": 0.3,
        "Boost": 0.2,
        "Unit-тестирование": 0.1,
        "SQL": 0.15,
    }),
    "gamedev": Profile(0.10, 1.05, {
        "C++": 0.97,
        "Unreal Engine": 0.5,
        "Unity": 0.15,
        "OpenGL": 0.25,
        "Vulkan": 0.15,
        "DirectX": 0.25,
        "C#": 0.2,
        "Алгоритмы и структуры данных": 0.3,
        "Математика": 0.3,
        "Linear algebra": 0.2,
        "STL": 0.35,
        "Git": 0.6,
        "Perforce": 0.15,
        "SIMD": 0.06,
        "Многопоточность": 0.3,
        "Lua": 0.12,
        "Python": 0.12,
        "Windows": 0.25,
    }),
    "hft": Profile(0.06, 1.9, {
        "C++": 1.0,
        "C++20": 0.45,
        "C++17": 0.4,
        "Low latency": 0.5,
        "Linux": 0.85,
        "Многопоточность": 0.6,
        "SIMD": 0.2,
        "TCP/IP": 0.4,
        "FIX protocol": 0.12,
        "Python": 0.35,
        "Алготрейдинг": 0.15,
        "Boost": 0.3,
        "Алгоритмы и структуры данных": 0.3,
        "Linux kernel": 0.08,
        "Git": 0.6,
        "CMake": 0.35,
        "Bash": 0.2,
        "STL": 0.3,
        "Rust": 0.04,
        "Технический английский": 0.2,
    }),
    "cv": Profile(0.09, 1.3, {
        "C++": 0.95,
        "OpenCV": 0.6,
        "CUDA": 0.25,
        "Python": 0.55,
        "Компьютерное зрение": 0.4,
        "Linear algebra": 0.25,
        "OpenMP": 0.12,
        "SIMD": 0.1,
        "Docker": 0.2,
        "ROS": 0.12,
        "Linux": 0.6,
        "Git": 0.6,
        "CMake": 0.35,
        "Математика": 0.3,
        "STL": 0.3,
        "Boost": 0.1,
        "Технический английский": 0.2,
    }),
    "legacy": Profile(0.10, 0.65, {
        "C++": 0.8,
        "MFC": 0.35,
        "Delphi": 0.25,
        "WinAPI": 0.3,
        "SVN": 0.3,
        "Pascal": 0.15,
        "Windows": 0.5,
        "SQL": 0.3,
        "ООП": 0.35,
        "Visual Studio": 0.35,
        "Access": 0.08,
        "C": 0.2,
        "Git": 0.15,
        "Алгоритмы и структуры данных": 0.1,
    }),
    "junior": Profile(0.08, 0.7, {
        "C": 0.5,
        "C++": 0.75,
        "ООП": 0.45,
        "Алгоритмы и структуры данных": 0.45,
        "STL": 0.35,
        "Git": 0.5,
        "Linux": 0.35,
        "SQL": 0.2,
        "Python": 0.2,
        "Паттерны проектирования": 0.1,
    }),
}
PROFILE_NAMES = list(PROFILES)

AREAS = {
    "Москва": Area(0.33, 1.25, {"hft": 2.2, "backend": 1.25, "cv": 1.2, "legacy": 0.8, "embedded": 0.7}),
    "Санкт-Петербург": Area(0.17, 1.10, {"gamedev": 2.2, "backend": 1.0, "embedded": 0.9, "cv": 1.2}),
    "Новосибирск": Area(0.055, 0.88, {"embedded": 2.0, "hft": 0.3, "gamedev": 0.5, "desktop": 1.2}),
    "Екатеринбург": Area(0.045, 0.95, {"embedded": 1.1, "backend": 1.1, "legacy": 1.3}),
    "Нижний Новгород": Area(0.045, 0.90, {"embedded": 1.8, "backend": 1.1}),
    "Казань": Area(0.035, 0.90, {"backend": 1.2, "gamedev": 1.2}),
    "Краснодар": Area(0.03, 0.90, {"legacy": 1.3, "desktop": 1.2}),
    "Самара": Area(0.025, 0.82, {"embedded": 1.5, "legacy": 1.3}),
    "Томск": Area(0.015, 0.80, {"embedded": 1.8, "cv": 1.3}),
    "Воронеж": Area(0.02, 0.80, {"embedded": 1.5, "legacy": 1.2}),
    "Ростов-на-Дону": Area(0.02, 0.85, {"legacy": 1.3}),
    "Пермь": Area(0.015, 0.82, {"embedded": 1.3, "legacy": 1.3}),
    "Челябинск": Area(0.012, 0.78, {"legacy": 1.5, "embedded": 1.2}),
    "Минск": Area(0.03, 0.80, {"backend": 1.2, "gamedev": 1.3}),
    "Другие регионы": Area(0.133, 0.75, {"legacy": 1.4, "junior": 1.5}),
}

# Требуемый опыт: (значение в данных, вероятность, множитель зарплаты)
EXPERIENCE_LEVELS = [
    ("noExperience", 0.18, 0.60),
    ("between1And3", 0.41, 1.00),
    ("between3And6", 0.29, 1.55),
    ("moreThan6", 0.12, 2.10),
]
SCHEDULES = [("fullDay", 0.68), ("remote", 0.18), ("flexible", 0.09), ("shift", 0.05)]
EMPLOYMENT_TYPES = [("full", 0.9), ("part", 0.04), ("project", 0.04), ("probation", 0.02)]

BASE_SALARY_RUB = 125_000  # на руки
INCOME_TAX_SHARE = 0.87    # доля зарплаты на руки, если в вакансии указана зарплата до вычета НДФЛ
SALARY_SHARE = 0.58        # доля вакансий с указанной зарплатой
GROSS_SHARE = 0.6          # доля вакансий, где зарплата указана до вычета НДФЛ
RUB_PER_CURRENCY = {"RUR": 1.0, "USD": 90, "EUR": 100, "KZT": 0.19}

EMPLOYER_COUNT = 4000
EMPLOYER_NAME_PREFIXES = [
    "Софт", "Инфо", "Нео", "Альфа", "Радио", "Техно", "Вектор", "Квант", "Спутник", "Кварц", "Орбита", "Нова",
    "Сигма", "Дата", "Мега", "Ультра", "Рубин", "Атом", "Эра", "Логика",
]
EMPLOYER_NAME_SUFFIXES = [
    "Системы", "Технологии", "Лаб", "Софт", "Групп", "Электроникс", "Решения", "Девелопмент", "Инжиниринг",
    "Сервис",
]

TITLES_BY_PROFILE = {
    "embedded": [
        "Программист C/C++ (встраиваемые системы)",
        "Embedded-разработчик",
        "Инженер-программист микроконтроллеров",
        "Разработчик ПО для embedded Linux",
    ],
    "backend": [
        "C++ разработчик (backend)",
        "Программист C++",
        "Senior C++ Developer",
        "Middle C++ разработчик",
    ],
    "desktop": [
        "C++/Qt разработчик",
        "Разработчик десктопных приложений на C++",
        "Программист C++ (Qt)",
    ],
    "gamedev": [
        "Game Developer (C++)",
        "Программист игрового движка",
        "Gameplay-программист C++",
    ],
    "hft": [
        "C++ Developer (Low latency)",
        "Разработчик торговых систем (C++)",
        "Quant Developer C++",
    ],
    "cv": [
        "C++ разработчик (компьютерное зрение)",
        "Инженер-программист CV",
        "Разработчик C++/CUDA",
    ],
    "legacy": [
        "Программист C++ (поддержка)",
        "Программист C++/Delphi",
        "Инженер-программист (MFC)",
    ],
    "junior": [
        "Junior C++ разработчик",
        "Стажёр-программист C/C++",
        "Программист C++ (начинающий)",
    ],
}

DESCRIPTION_SENTENCES = [
    "Мы разрабатываем собственные продукты и ищем в команду сильного специалиста.",
    "Вам предстоит участвовать в проектировании и разработке новых модулей системы.",
    "Работа в дружной команде, поддержка менторов, возможность расти внутри компании.",
    "Оформление по ТК РФ, ДМС, компенсация обучения и конференций.",
    "Гибкое начало рабочего дня, возможность частичной удалённой работы.",
    "Мы ожидаем от кандидата опыт коммерческой разработки и умение читать чужой код.",
    "Вы будете заниматься оптимизацией производительности и отладкой сложных ошибок.",
    "Участие в код-ревью, написание тестов и технической документации.",
    "Взаимодействие с аналитиками, тестировщиками и смежными командами.",
    "Современные инструменты разработки и автоматизированная сборка.",
    "Работа над высоконагруженным и отказоустойчивым ПО.",
    "Своевременная выплата заработной платы, прозрачная система премирования.",
]

CSV_HEADER = [
    "source",
    "vacancy_id",
    "status",
    "snapshot_date",
    "published_at",
    "area",
    "employer_id",
    "employer_inn",
    "employer_ogrn",
    "employer_name",
    "name",
    "role",
    "sphere",
    "salary_from",
    "salary_to",
    "currency",
    "gross",
    "experience",
    "schedule",
    "employment",
    "key_skills",
    "description",
    "url",
]


def choose_weighted(rng, options_with_weights):
    options, weights = zip(*options_with_weights)

    return rng.choices(options, weights=weights, k=1)[0]


def write_alias_file(path):
    """
    Словарь синонимов для нормализации: написание в нижнем регистре -> каноническое название.
    """
    alias_to_skill = {}
    for canonical_skill, spellings in SKILL_SPELLINGS.items():
        for spelling in [canonical_skill] + spellings:
            alias_to_skill[spelling.strip().lower()] = canonical_skill

    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["alias", "skill"])
        for alias in sorted(alias_to_skill):
            writer.writerow([alias, alias_to_skill[alias]])


def generate_cpp_vacancy(rng, area_names, area_weights):
    """
    Регион, профиль и список навыков для одной C/C++ вакансии.
    """
    area_name = rng.choices(area_names, weights=area_weights, k=1)[0]
    area = AREAS[area_name]

    profile_weights = [
        PROFILES[name].share * area.profile_multipliers.get(name, 1.0)
        for name in PROFILE_NAMES
    ]
    profile_name = rng.choices(PROFILE_NAMES, weights=profile_weights, k=1)[0]
    profile = PROFILES[profile_name]

    # Каждый навык профиля включается независимо со своей вероятностью
    skills = [
        skill
        for skill, probability in profile.skill_probabilities.items()
        if rng.random() < probability
    ]

    # Один-два случайных навыка из общего словаря и редкие навыки
    for _ in range(rng.choice([0, 0, 1, 1, 2])):
        skills.append(rng.choice(list(SKILL_SPELLINGS)))
    if rng.random() < 0.05:
        skills.append(rng.choice(RARE_SKILLS))
    if rng.random() < 0.03:
        skills = []

    seen_skills = set()
    unique_skills = []
    for skill in skills:
        if skill not in seen_skills:
            seen_skills.add(skill)
            unique_skills.append(skill)
    rng.shuffle(unique_skills)

    return area_name, area.salary_multiplier, profile_name, profile.salary_multiplier, unique_skills


def pick_spelling(rng, skill):
    """
    Случайное написание навыка; каноническое написание встречается чаще остальных.
    """
    if skill in SKILL_SPELLINGS:
        return rng.choice(SKILL_SPELLINGS[skill] + [skill] * 3)

    return skill


def make_salary_fields(rng, base_salary_rub):
    """
    Поля salary_from, salary_to, currency, gross для вакансии с зарплатой.
    """
    currency = rng.choices(["RUR", "USD", "EUR", "KZT"], weights=[0.93, 0.03, 0.01, 0.03])[0]
    is_gross = rng.random() < GROSS_SHARE

    # В вакансии зарплату указывают до вычета НДФЛ или на руки
    salary_rub = base_salary_rub / (INCOME_TAX_SHARE if is_gross else 1.0)
    salary_in_currency = salary_rub * (1 / RUB_PER_CURRENCY[currency])

    rounding_step = 1000 if currency in ("RUR", "KZT") else 100
    lower_bound = round(salary_in_currency * 0.9 / rounding_step) * rounding_step
    upper_bound = round(salary_in_currency * 1.1 / rounding_step) * rounding_step
    if currency == "KZT":
        lower_bound = round(lower_bound / 10000) * 10000
        upper_bound = round(upper_bound / 10000) * 10000

    point_value = round(salary_in_currency / rounding_step) * rounding_step
    shape_roll = rng.random()
    if shape_roll < 0.45:
        salary_from, salary_to = lower_bound, upper_bound  # вилка
    elif shape_roll < 0.8:
        salary_from, salary_to = point_value, ""           # только «от»
    else:
        salary_from, salary_to = "", point_value           # только «до»

    return salary_from, salary_to, currency, "true" if is_gross else "false"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=250_000)
    parser.add_argument("--cpp-share", type=float, default=0.20, help="share of C/C++ vacancies")
    parser.add_argument("--seed", type=int, default=2024)
    parser.add_argument("--out", default="data/it_vacancies_2024.csv")
    parser.add_argument("--alias-out", default="data/skills_alias.csv")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    numpy_rng = np.random.default_rng(args.seed)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    write_alias_file(args.alias_out)

    area_names = list(AREAS)
    area_weights = [AREAS[name].weight for name in area_names]
    other_role_names = list(OTHER_ROLES)
    first_day = date(2024, 1, 15)

    employers = []
    for employer_index in range(EMPLOYER_COUNT):
        inn = str(rng.randrange(10**9, 10**10 - 1)).zfill(10)
        ogrn = str(rng.randrange(10**12, 10**13 - 1))
        name_prefix = rng.choice(EMPLOYER_NAME_PREFIXES)
        name_suffix = rng.choice(EMPLOYER_NAME_SUFFIXES)
        employers.append((
            str(1_000_000 + employer_index * 7),
            inn,
            ogrn,
            f"ООО «{name_prefix}{name_suffix}»",
        ))

    experience_names = [level[0] for level in EXPERIENCE_LEVELS]
    experience_probabilities = [level[1] for level in EXPERIENCE_LEVELS]
    experience_multipliers = {level[0]: level[2] for level in EXPERIENCE_LEVELS}

    with open(args.out, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(CSV_HEADER)

        vacancy_id = 90_000_000
        for _ in range(args.rows):
            vacancy_id += rng.randrange(1, 40)
            published_date = first_day + timedelta(days=rng.randrange(0, 300))
            snapshot_date = published_date + timedelta(days=rng.randrange(1, 60))
            employer = rng.choice(employers)
            experience = rng.choices(experience_names, weights=experience_probabilities)[0]
            experience_multiplier = experience_multipliers[experience]
            schedule = choose_weighted(rng, SCHEDULES)
            employment = choose_weighted(rng, EMPLOYMENT_TYPES)

            if rng.random() < args.cpp_share:
                role = CPP_ROLE
                area_name, area_multiplier, profile_name, profile_multiplier, skills = generate_cpp_vacancy(
                    rng, area_names, area_weights,
                )
                title = rng.choice(TITLES_BY_PROFILE[profile_name])

                skills_multiplier = 1.0
                for skill in skills:
                    skills_multiplier *= SKILL_SALARY_EFFECT.get(skill, 1.0)

                noise = float(np.exp(numpy_rng.normal(0, 0.22)))
                base_salary = (
                    BASE_SALARY_RUB * area_multiplier * profile_multiplier
                    * experience_multiplier * skills_multiplier * noise
                )
                if schedule == "remote":
                    base_salary *= 1.04
            else:
                role = choose_weighted(rng, list(zip(other_role_names, OTHER_ROLE_WEIGHTS)))
                area_name = rng.choices(area_names, weights=area_weights, k=1)[0]
                skill_pool = OTHER_ROLES[role]
                skills = rng.sample(skill_pool, min(len(skill_pool), rng.randrange(2, 9)))
                if rng.random() < 0.06:
                    skills.append(rng.choice(FOREIGN_SKILLS_IN_OTHER_ROLES))

                short_role = role.replace("Программист, разработчик на ", "")
                title = f"Разработчик {short_role}" if short_role != role else role

                noise = float(np.exp(numpy_rng.normal(0, 0.25)))
                base_salary = BASE_SALARY_RUB * AREAS[area_name].salary_multiplier * experience_multiplier * noise

            key_skills = ", ".join(pick_spelling(rng, skill) for skill in skills)

            salary_from, salary_to, currency, gross = "", "", "", ""
            if rng.random() < SALARY_SHARE:
                salary_from, salary_to, currency, gross = make_salary_fields(rng, base_salary)

            description_sentences = rng.sample(DESCRIPTION_SENTENCES, rng.randrange(3, 8))
            description = " ".join(description_sentences)
            if key_skills:
                description += f' Ключевые требования: {key_skills}. Опыт: "{experience}".'

            writer.writerow([
                "hh.ru",
                vacancy_id,
                "open",
                snapshot_date.isoformat(),
                published_date.isoformat() + "T10:00:00+0300",
                area_name,
                employer[0],
                employer[1],
                employer[2],
                employer[3],
                title,
                role,
                "IT",
                salary_from,
                salary_to,
                currency,
                gross,
                experience,
                schedule,
                employment,
                key_skills,
                description,
                f"https://hh.ru/vacancy/{vacancy_id}",
            ])

    print("done:", args.out)


if __name__ == "__main__":
    main()
