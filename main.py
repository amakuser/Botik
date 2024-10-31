from itertools import count

indexed_chars = {}

def length_price(*, price: str) -> tuple:
    for i, char in enumerate(reversed(price)):
        indexed_chars[-(i + 1)] = char

    index = next((key for key, value in indexed_chars.items() if value == "."), None)

    if index is not None:
        before_the_index = index - 1
        after_the_index = index + 1
        price_replesed = price.replace(".", "")

        # Удаляем индекс с точкой из словаря
        del indexed_chars[index]

        return before_the_index, after_the_index, price_replesed  # Возвращаем три переменные
    else:
        return None, None, None  # Если точка не найдена, возвращаем None

result_before_bid, result_after_bid, price_without_a_point = length_price(price="78.999")
print("Индекс перед точкой:", result_before_bid)
print("Индекс после точки:", result_after_bid)
print("Цена без точки:", price_without_a_point)

def price(*, price_without_a_point: str) -> str:
    # Обновляем indexed_chars на основе нового значения price_without_a_point
    indexed_chars.clear()  # Очищаем словарь перед новым использованием
    for i, char in enumerate(reversed(price_without_a_point)):
        indexed_chars[-(i + 1)] = char

    for key in sorted(indexed_chars.keys(), reverse=True):
        value = indexed_chars[key]

        # Проверяем, является ли значение цифрой
        if value.isdigit():
            if int(value) == 9:
                # Если значение 9, меняем на 0
                indexed_chars[key] = '0'
            else:
                # Увеличиваем на 1 и завершаем цикл
                indexed_chars[key] = str(int(value) + 1)
            # Собираем результирующую строку после изменения
            break

    result_string = ''.join(indexed_chars.values())
    reversed_result_string = result_string[::-1]
    return reversed_result_string

otvet = price(price_without_a_point=price_without_a_point)
print("Измененная цена:", otvet)
