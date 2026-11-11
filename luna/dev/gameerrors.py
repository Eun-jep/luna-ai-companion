"""Known game-engine errors: when he pastes an error or log line from an engine ("Invalid call. Nonexistent function 'x' in base 'Nil'", "CS0246", "LNK2019", "NullReferenceException"...),
the program recognises it by its fixed text, which does not depend on his language, and gives her a checked note: what it usually means and what to check first. She retells it in his
language; anything the table does not know she says honestly she cannot tell for sure. Only the matched lines of the pasted text are used, nothing is run."""
import re

# (engine, regex, meaning, what to check)
ERRORS = [
    ('Godot', r"Invalid (?:call|get index|set index).*(?:base 'Nil'|on base: 'Nil')|Nonexistent function .* in base 'Nil'|on a null instance",
     'обращение к узлу или переменной, которая пустая (null/Nil)', 'путь в $Node или get_node верный? узел уже в дереве (после _ready)? переменная с @onready действительно присвоена?'),
    ('Godot', r"Node not found: ", 'get_node/$ не нашёл узел по этому пути', 'имя узла и регистр, относительный путь от скрипта; узел мог быть переименован или создаётся позже'),
    ('Godot', r"Parser Error: .*(?:Identifier|identifier) .* not declared", 'переменная или функция не объявлена в этой области', 'опечатка в имени, var объявлен в другой функции, забытый extends или const'),
    ('Godot', r"Parser Error: .*Mixed use of tabs and spaces|Unexpected indent|Expected indented block", 'отступы в GDScript перепутаны', 'один стиль отступов на файл: либо табы, либо пробелы'),
    ('Godot', r"Cannot (?:infer|assign) .*type|Trying to assign value of type", 'несовместимые типы при присваивании', 'явно укажи тип или приведи значение (int(), float(), as Type)'),
    ('Godot', r"Failed to load resource|Resource file not found|res://.* not found|Cannot open file", 'ресурс по пути res:// не найден', 'файл переместили или переименовали? путь с учётом регистра; после правки пересканируй файловую систему'),
    ('Godot', r"ERROR: .*\.godot|Can't open dynamic library|GDExtension", 'не загрузилось расширение (GDExtension)', 'версия Godot и расширения должны совпадать; проверь .gdextension и путь к библиотеке'),
    ('Unity', r"NullReferenceException", 'обращение к объекту, который не назначен', 'поле в Inspector пустое? GetComponent вернул null? объект уничтожен? в стеке смотри первую строку со своим скриптом'),
    ('Unity', r"error CS0246|The type or namespace name .* could not be found", 'не найден тип или пространство имён', 'не хватает using, пакета (Package Manager) или assembly definition; опечатка в имени класса'),
    ('Unity', r"error CS0103|does not exist in the current context", 'имя не существует в этом контексте', 'переменная объявлена в другой области, опечатка, регистр букв'),
    ('Unity', r"error CS1061|does not contain a definition for", 'у типа нет такого члена', 'метод или поле названы иначе, другая версия API, неверный тип переменной'),
    ('Unity', r"MissingReferenceException|MissingComponentException", 'объект уничтожен или компонента нет', 'не обращайся к Destroy-нутому объекту; проверь на null; проверь RequireComponent'),
    ('Unity', r"The referenced script .* on this Behaviour .* is missing|script class cannot be found", 'у скрипта на объекте нет класса', 'имя файла и имя класса должны совпадать; скрипт должен компилироваться без ошибок'),
    ('Unity', r"IndexOutOfRangeException|ArgumentOutOfRangeException", 'индекс за пределами массива или списка', 'проверь длину перед обращением, особенно когда список пуст'),
    ('Unreal', r"LNK2019|LNK2001|unresolved external symbol", 'линкер не нашёл реализацию', 'модуль не добавлен в PublicDependencyModuleNames в .Build.cs; функция объявлена, но не определена'),
    ('Unreal', r"Cannot open include file|fatal error C1083", 'не найден заголовок', 'добавь модуль в Build.cs, проверь путь include и регистр; пересобери проект (Generate Project Files)'),
    ('Unreal', r"Access violation|EXCEPTION_ACCESS_VIOLATION|Fatal error: \[File:", 'падение из-за обращения к пустому или удалённому указателю', 'проверь IsValid()/nullptr перед использованием, UPROPERTY для указателей на UObject, порядок инициализации'),
    ('Unreal', r"Could not be compiled\. Try rebuilding from source manually|Module .* could not be loaded", 'модуль проекта не собрался', 'закрой редактор, пересобери из Visual Studio и прочитай первую ошибку компилятора выше'),
    ('Unreal', r"Accessed None trying to read property", 'Blueprint читает свойство у пустой ссылки', 'ссылка не присвоена или объект ещё не создан; поставь Is Valid перед использованием'),
    ('GameMaker', r"Variable .*(?:not set before reading it|<unknown_object>)|unable to find any instance for object index", 'чтение переменной или обращение к экземпляру, которого нет', 'инициализируй переменную в Create; проверь instance_exists перед обращением'),
    ('GameMaker', r"Unable to convert string .* to number|Illegal use of", 'тип значения не тот (строка вместо числа и т.п.)', 'приведи real()/string() явно и проверь, что в переменной нужный тип'),
    ('Bevy', r"error\[E0499\]|error\[E0502\]|cannot borrow .* as mutable", 'нарушено правило заимствований Rust', 'не держи две ссылки на одно и то же; в Bevy раздели запросы Query (Without<T>) или используй ParamSet'),
    ('Bevy', r"Resource requested by .* does not exist|Could not find resource", 'система просит ресурс, который не добавлен', 'добавь app.insert_resource / init_resource или нужный Plugin до запуска'),
    ('Phaser', r"Cannot read propert(?:y|ies).* of undefined|TypeError: .* is not a function", 'объект или метод не существует в этот момент', 'ресурс не загружен (грузи в preload), this.x вызван до create, потеряно this в колбэке (используй стрелочную функцию)'),
    ('Phaser', r"Failed to process file: (?:image|audio|spritesheet|atlas)|Texture key .* not found|missing texture", 'ресурс не загрузился или ключ неверный', 'путь относительно сервера, ключ совпадает с тем, что в this.load; открывай через локальный сервер, не файлом'),
    ('Web', r"CORS|Access-Control-Allow-Origin|blocked by CORS", 'браузер запретил загрузку файла с другого источника', 'запускай через локальный сервер (npm run dev, python -m http.server), а не двойным кликом'),
    ('LÖVE', r"Error: .*main\.lua:\d+:.*attempt to (?:index|call|perform arithmetic on) a nil value|attempt to index a nil value", 'Lua обратилась к пустому значению', 'таблица или функция не создана до вызова; опечатка в имени поля; проверь порядок love.load и love.update'),
    ('Lua', r"attempt to compare number with nil|attempt to concatenate a nil value", 'в выражении пустое значение', 'инициализируй переменную значением по умолчанию; проверь, что функция что-то возвращает'),
    ('Defold', r"ERROR:SCRIPT:.*|attempt to index a nil value.*\.script", 'ошибка в Lua-скрипте Defold', 'проверь, что self.* создан в init, а id объектов и url (msg.url) написаны верно'),
    ("Ren'Py", r"IndentationError|is not a keyword argument or valid child of the (?:text|image|vbox)|could not find (?:image|label)", 'ошибка в сценарии .rpy', 'отступы только пробелами, метка (label) существует, картинка объявлена через image и лежит в game/images'),
    ('Pygame', r"pygame\.error: (?:No available video device|video system not initialized|display Surface quit)", 'окно pygame не инициализировано или закрыто', 'вызови pygame.init() и pygame.display.set_mode() до рисования; не рисуй после pygame.quit()'),
    ('Python', r"ModuleNotFoundError: No module named", 'модуль не установлен в этом окружении', 'pip install нужный пакет тем же интерпретатором, которым запускаешь игру (python -m pip install ...)'),
    ('Unity/MonoBehaviour', r"You are trying to create a MonoBehaviour using the 'new' keyword|UnassignedReferenceException", 'компонент создан неправильно или поле не назначено', 'MonoBehaviour добавляют через AddComponent, а ссылки перетаскивают в Inspector'),
    ('Shader', r"undeclared identifier|syntax error: unexpected|Shader error in", 'ошибка компиляции шейдера', 'смотри первую строку и номер строки в сообщении; типы float/half, регистр имён, точка с запятой'),
]
_COMPILED = [(e, re.compile(r, re.I), m, c) for e, r, m, c in ERRORS]
MAX_NOTES = 3


def match(text):
    """[(engine, meaning, check)] for the known errors seen in the text, in order of the table, at most three."""
    text = str(text or '')[:6000]
    if len(text) < 12:
        return []
    out = []
    for engine, rx, meaning, check in _COMPILED:
        if rx.search(text) and (engine, meaning) not in [(o[0], o[1]) for o in out]:
            out.append((engine, meaning, check))
    return out[:MAX_NOTES]


def hint(text):
    found = match(text)
    if not found:
        return ''
    lines = ' | '.join('%s: %s; сначала проверь: %s' % f for f in found)
    return ('[Программа узнала в его сообщении известную ошибку движка по её тексту: %s. Объясни ему это простыми словами на его языке и назови, что проверить, '
            'но это типичные причины, а не диагноз: если файла ты не видела, так и скажи и предложи прочитать нужный скрипт.]' % lines)
