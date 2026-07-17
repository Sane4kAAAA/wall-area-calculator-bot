import math
import asyncio
from back import keep_alive
from typing import List, Tuple
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, ReplyKeyboardRemove


# Класс состояний
class Form(StatesGroup):
    room_name = State()
    room_shape = State()
    rectangle_dim = State()
    triangle_dim = State()
    circle_dim = State()
    polygon_sides = State()
    room_height = State()
    add_unused = State()
    unused_height = State()
    unused_width = State()
    another_room = State()


class Room:
    def __init__(self, name, shape_type, dimensions, height, unused_surfaces):
        self.name = name
        self.shape_type = shape_type.lower().replace('гольник', 'угольник')
        self.dimensions = dimensions
        self.height = height
        self.unused_surfaces = unused_surfaces

    def calculate_perimeter(self):
        shape_type = self.shape_type.lower().replace('гольник', 'угольник')  # Исправляем опечатку
        if shape_type == 'rectangle':
            length, width = self.dimensions
            return 2 * (length + width)
        elif shape_type == 'triangle':
            a, b, c = self.dimensions
            return a + b + c
        elif shape_type == 'circle':
            radius, = self.dimensions
            return 2 * math.pi * radius
        elif self.shape_type == 'polygon':
            n, side_length = self.dimensions
            print(f"Отладка (периметр): {n} сторон × {side_length} м")  # Для проверки
            return n * side_length
        raise ValueError(f"Неизвестный тип комнаты: {self.shape_type}")

    def calculate_wall_area(self):
        perimeter = self.calculate_perimeter()
        print(f"Отладка (стены): {perimeter} м × {self.height} м")  # Должно быть 20 × 3
        return perimeter * self.height

    def net_wall_area(self):
        return self.calculate_wall_area() - self.calculate_unused_area()

    def calculate_floor_area(self):
        if self.shape_type == 'rectangle':
            length, width = self.dimensions
            return length * width
        elif self.shape_type == 'triangle':
            a, b, c = self.dimensions
            p = (a + b + c) / 2
            return math.sqrt(abs(p * (p - a) * (p - b) * (p - c)))  # abs для избежания ошибок округления
        elif self.shape_type == 'circle':
            radius, = self.dimensions
            return math.pi * radius ** 2
        elif self.shape_type == 'polygon':
            n, side_length = self.dimensions  # n - количество сторон, side_length - длина стороны
            if n < 3:
                return 0.0
            area = (n * side_length ** 2) / (4 * math.tan(math.pi / n))
            return abs(round(area, 2))  # Берём модуль и округляем
        return 0.0

    def calculate_unused_area(self):
        return sum(h * w for h, w in self.unused_surfaces)


class Building:
    def __init__(self):
        self.rooms = []

    def add_room(self, room):
        self.rooms.append(room)

    def total_wall_area(self):
        return sum(room.net_wall_area() for room in self.rooms)

    def living_rooms_area(self):
        return sum(room.net_wall_area() for room in self.rooms
                   if 'жилая' in room.name.lower() or 'living' in room.name.lower())

    def total_floor_space(self):
        return sum(max(0, room.calculate_floor_area()) for room in self.rooms)


# Хранилище данных
user_data = {}


async def reset_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            'building': Building(),
            'current_room': None,
            'unused': [],
        }
    else:
        # Не сбрасываем здание, только текущие данные комнаты
        user_data[user_id]['current_room'] = None
        user_data[user_id]['unused'] = []


# Инициализация бота
bot = Bot(token="YOUR_BOT_TOKEN")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Команды
@dp.message(Command("start", "help"))
async def start(message: Message):
    markup = ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="Начать расчет")]],
        resize_keyboard=True
    )
    await message.answer(
        "🏠 Бот для расчета площадей стен помещений\n\n"
        "Поддерживаемые формы помещений: прямоугольные, треугольные, круглые, многоугольные\n\n"
        "Команды:\n"
        "/start - начать новый расчет\n"
        "/cancel - отменить текущую операцию\n\n"
        "Нажмите кнопку ниже чтобы начать:",
        reply_markup=markup
    )


@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена", reply_markup=ReplyKeyboardRemove())


@dp.message(lambda message: message.text == "Начать расчет")
async def start_calculation(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await reset_user_data(user_id)
    await state.set_state(Form.room_name)
    await message.answer("Введите название помещения:", reply_markup=ReplyKeyboardRemove())


# Основной диалог
@dp.message(Form.room_name)
async def process_room_name(message: types.Message, state: FSMContext):
    await state.update_data(room_name=message.text)

    markup = ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Прямоугольник")],
            [types.KeyboardButton(text="Треугольник")],
            [types.KeyboardButton(text="Круг")],
            [types.KeyboardButton(text="Многоугольник")]
        ],
        resize_keyboard=True
    )

    await state.set_state(Form.room_shape)
    await message.answer("Выберите форму помещения:", reply_markup=markup)


@dp.message(Form.room_shape)
async def process_room_shape(message: types.Message, state: FSMContext):
    # Нормализуем ввод: удаляем пробелы и приводим к нижнему регистру
    shape = message.text.strip().lower()

    # Допустимые варианты (учитываем возможные опечатки)
    valid_shapes = {
        'прямоугольник': 'rectangle',
        'треугольник': 'triangle',
        'круг': 'circle',
        'многоугольник': 'polygon'
    }

    # Проверяем нормализованный ввод
    if shape not in valid_shapes:
        # Создаем клавиатуру с правильными вариантами
        markup = ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="Прямоугольник")],
                [types.KeyboardButton(text="Треугольник")],
                [types.KeyboardButton(text="Круг")],
                [types.KeyboardButton(text="Многоугольник")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Пожалуйста, выберите вариант из предложенных:",
            reply_markup=markup
        )
        return

    # Сохраняем английское название для удобства обработки
    await state.update_data(room_shape=valid_shapes[shape])

    # Определяем следующий шаг в зависимости от формы
    next_steps = {
        'rectangle': Form.rectangle_dim,
        'triangle': Form.triangle_dim,
        'circle': Form.circle_dim,
        'polygon': Form.polygon_sides
    }
    await state.set_state(next_steps[valid_shapes[shape]])

    # Запрашиваем параметры для конкретной формы
    prompts = {
        'rectangle': "Введите длину и ширину через пробел (например: 5 4):",
        'triangle': "Введите длины 3 сторон через пробел (например: 3 4 5):",
        'circle': "Введите радиус комнаты:",
        'polygon': "Введите количество сторон и длину стороны через пробел (например: 5 4):"
    }
    await message.answer(prompts[valid_shapes[shape]], reply_markup=ReplyKeyboardRemove())

# Обработчики ввода параметров
@dp.message(Form.rectangle_dim)
async def process_rectangle_dim(message: types.Message, state: FSMContext):
    try:
        length, width = map(float, message.text.split())
        if length <= 0 or width <= 0:
            raise ValueError

        await state.update_data(dimensions=(length, width))
        await state.set_state(Form.room_height)
        await message.answer("Введите высоту помещения (в метрах):")
    except:
        await message.answer("❗ Некорректные значения. Введите два положительных числа через пробел")


@dp.message(Form.triangle_dim)
async def process_triangle_dim(message: types.Message, state: FSMContext):
    try:
        a, b, c = map(float, message.text.split())
        if a <= 0 or b <= 0 or c <= 0:
            raise ValueError
        if a + b <= c or a + c <= b or b + c <= a:
            await message.answer("❗ Такой треугольник не существует. Введите корректные длины сторон")
            return

        await state.update_data(dimensions=(a, b, c))
        await state.set_state(Form.room_height)
        await message.answer("Введите высоту помещения (в метрах):")
    except:
        await message.answer("❗ Некорректные значения. Введите три положительных числа через пробел")


@dp.message(Form.circle_dim)
async def process_circle_dim(message: types.Message, state: FSMContext):
    try:
        radius = float(message.text)
        if radius <= 0:
            raise ValueError

        await state.update_data(dimensions=(radius,))
        await state.set_state(Form.room_height)
        await message.answer("Введите высоту помещения (в метрах):")
    except:
        await message.answer("❗ Некорректное значение. Введите положительное число")


@dp.message(Form.polygon_sides)
async def process_polygon_sides(message: types.Message, state: FSMContext):
    try:
        # Ожидаем два числа: количество сторон и длину стороны
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❗ Введите два числа через пробел: количество сторон и длину стороны (например: 5 4)")
            return

        n = int(parts[0])
        side_length = float(parts[1])  # Было 'side', исправлено на 'side_length'

        if n < 3:
            await message.answer("❗ Многоугольник должен иметь минимум 3 стороны")
            return
        if side_length <= 0:  # Теперь используем side_length вместо side
            await message.answer("❗ Длина стороны должна быть положительной")
            return

        await state.update_data(dimensions=(n, side_length))  # Исправлено здесь
        await state.set_state(Form.room_height)
        await message.answer("Введите высоту помещения (в метрах):")
    except ValueError:
        await message.answer("❗ Некорректные значения. Введите целое число сторон и длину стороны (например: 5 4)")

@dp.message(Form.room_height)
async def process_room_height(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        height = float(message.text.replace(',', '.'))
        if height <= 0:
            raise ValueError("Высота должна быть положительной")

        data = await state.get_data()
        print(f"Данные для создания комнаты: {data}")  # Отладочный вывод

        # Проверка наличия всех необходимых данных
        if 'room_name' not in data or 'room_shape' not in data or 'dimensions' not in data:
            raise ValueError("Не хватает данных для создания комнаты")

        user_data[user_id]['current_room'] = Room(
            name=data['room_name'],
            shape_type=data['room_shape'],
            dimensions=data['dimensions'],
            height=height,
            unused_surfaces=[]
        )

        # Проверка создания комнаты
        if not user_data[user_id]['current_room']:
            raise ValueError("Не удалось создать объект комнаты")

        markup = ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="Да"), types.KeyboardButton(text="Нет")]],
            resize_keyboard=True
        )
        await state.set_state(Form.add_unused)
        await message.answer("Добавить окно/дверной проем?", reply_markup=markup)

    except ValueError as e:
        await message.answer(f"❗ Ошибка: {e}")
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        await message.answer("❗ Произошла непредвиденная ошибка")


@dp.message(Form.add_unused)
async def process_add_unused(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text.lower() == 'да':
        await state.set_state(Form.unused_height)
        await message.answer("Введите высоту проема (в метрах):", reply_markup=ReplyKeyboardRemove())
    else:
        # Проверяем, не добавлена ли комната ранее
        current_room = user_data[user_id]['current_room']
        building = user_data[user_id]['building']

        if current_room.name not in [r.name for r in building.rooms]:  # Если имя комнаты уникально
            current_room.unused_surfaces = user_data[user_id]['unused'].copy()
            building.add_room(current_room)
            print(f"Комната '{current_room.name}' добавлена в здание.")  # Логируем
        else:
            print(f"Комната '{current_room.name}' уже существует!")  # Предупреждение

        markup = ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="Да"), types.KeyboardButton(text="Нет")]],
            resize_keyboard=True
        )
        await state.set_state(Form.another_room)
        await message.answer("Добавить еще одно помещение?", reply_markup=markup)

@dp.message(Form.unused_height)
async def process_unused_height(message: types.Message, state: FSMContext):
    try:
        height = float(message.text)
        if height <= 0:
            raise ValueError

        await state.update_data(unused_height=height)
        await state.set_state(Form.unused_width)
        await message.answer("Введите ширину проема (в метрах):")
    except:
        await message.answer("❗ Некорректное значение. Введите число больше 0:")


@dp.message(Form.unused_width)
async def process_unused_width(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        width = float(message.text)
        if width <= 0:
            raise ValueError

        data = await state.get_data()
        height = data.get('unused_height', 0)

        user_data[user_id]['unused'].append((height, width))

        markup = ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="Да"), types.KeyboardButton(text="Нет")]],
            resize_keyboard=True
        )

        await state.set_state(Form.add_unused)
        await message.answer("Добавить еще один проем?", reply_markup=markup)
    except:
        await message.answer("❗ Некорректное значение. Введите число больше 0:")


@dp.message(Form.another_room)
async def process_another_room(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    building = user_data[user_id]['building']

    # Формируем детализированный отчет
    result = [
        "📊 Детализированные результаты:",
        "",
        f"• Общая площадь стен: {building.total_wall_area():.2f} м²",
        #f"• Площадь жилых комнат: {building.living_rooms_area():.2f} м²",
        f"• Общая площадь помещений: {building.total_floor_space():.2f} м²",
        "",
        "🔎 Детали по комнатам:"
    ]

    # Добавляем информацию по каждой комнате
    for i, room in enumerate(building.rooms, 1):
        result.extend([
            f"",
            f"{i}. {room.name}:",
           # f"  - Тип: {room.shape_type}",
            f"  - Площадь стен: {room.net_wall_area():.2f} м²",
            f"  - Площадь помещения: {room.calculate_floor_area():.2f} м²",
            f"  - Высота: {room.height} м"
        ])

    result.append("")
    result.append("Выберите действие:")

    # Отправляем форматированное сообщение
    await message.answer("\n".join(result))

    # Создаем клавиатуру с двумя кнопками
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Начать новый расчет")],
            [types.KeyboardButton(text="Продолжить расчет")]
        ],
        resize_keyboard=True
    )
    await message.answer("Что делаем дальше?", reply_markup=markup)

    # Обработка выбора
    if message.text == "Начать новый расчет":
        await reset_user_data(user_id)
        await state.clear()
        await message.answer("Все данные сброшены. Введите название помещения:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.room_name)

    elif message.text == "Продолжить расчет":
        user_data[user_id]['current_room'] = None
        user_data[user_id]['unused'] = []
        await state.set_state(Form.room_name)
        await message.answer("Введите название нового помещения:", reply_markup=ReplyKeyboardRemove())

# Обновленная функция reset_user_data
async def reset_user_data(user_id, full_reset=True):
    if full_reset:
        # Полный сброс (для "Начать новый расчет")
        user_data[user_id] = {
            'building': Building(),
            'current_room': None,
            'unused': []
        }
    else:
        # Частичный сброс (для "Продолжить расчет")
        if user_id in user_data:
            user_data[user_id]['current_room'] = None
            user_data[user_id]['unused'] = []


async def main():
    await dp.start_polling(bot)

keep_alive()
if __name__ == '__main__':
    asyncio.run(main())