from itertools import count
from collections import OrderedDict

indexed_chars_bid = {}
indexed_chars_ask = {}

def length_price(*, price: str) -> tuple:
    for i, char in enumerate(reversed(price)):
        indexed_chars_bid[-(i + 1)] = char

    index = next((key for key, value in indexed_chars_bid.items() if value == "."), None)

    if index is not None:
        before_the_index = index - 1
        after_the_index = index + 1
        price_replesed = price.replace(".", "")

        # Удаляем индекс с точкой из словаря
        del indexed_chars_bid[index]

        return before_the_index, after_the_index, price_replesed  # Возвращаем три переменные
    else:
        return None, None, None  # Если точка не найдена, возвращаем None

result_before_bid, result_after_bid, price_without_a_point_bid = length_price(price="99.999")
print("Индекс перед точкой:", result_before_bid)
print("Индекс после точки:", result_after_bid)
print("Цена без точки:", price_without_a_point_bid)

def price_bid(*, price_bid = str) -> str:
    indexed_chars_bid = {f"-{i + 1}": int(char) for i, char in enumerate(reversed(price_bid))}
    for key, value in indexed_chars_bid.items():
        if value == 9:
            indexed_chars_bid[key] = 0

        else:
            value = value + 1
            indexed_chars_bid[key] = value
            break
    last_value = indexed_chars_bid[list(indexed_chars_bid.keys())[-1]]
    my_dict = OrderedDict(indexed_chars_bid)
    if last_value == 0:
        count = len(indexed_chars_bid)
        count -= 1
        keys = list(indexed_chars_bid.keys())
        key = keys[count]
        value = indexed_chars_bid[key]
        count += 2
        count = f"-{count}"
        my_dict.update({count: 1})
    result = ''.join(str(value) for value in my_dict.values())
    return result[::-1]

otvet_bid = price_bid(price_bid=price_without_a_point_bid)
print("Измененная цена покупки:", otvet_bid)

result_before_ask, result_after_ask, price_without_a_point_ask = length_price(price="79.005")
print("Индекс перед точкой:", result_before_ask)
print("Индекс после точки:", result_after_ask)
print("Цена без точки:", price_without_a_point_ask)


def price_ask(*, price_ask = str) -> str:
    indexed_chars_ask = {f"-{i + 1}": int(char) for i, char in enumerate(reversed(price_ask))}
    for key, value in indexed_chars_ask.items():
        if value == 0:
            indexed_chars_ask[key] = 9
            continue
        else:
            value = value - 1
            indexed_chars_ask[key] = value
            break
    result = ''.join(str(value) for value in indexed_chars_ask.values())
    return result[::-1]


result_after = price_ask(price_ask = "99999")
print("Измененная цена:", result_after)
