import json
from enum import Enum



class AskOrBid(Enum):
    ASK = "ask"
    BID = "bid"

class PositiveOrNegative(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"

class TrackingTheFunction(Enum):
    NOT_EXECUTED = 0
    EXECUTED = 1
function_state = TrackingTheFunction.NOT_EXECUTED


class JsonDataPrice:



    def __init__(self, json_str):
        self.data = json.loads(json_str)


    def update_price(self, new_price: AskOrBid, price_itself: str ): # записываем цену по выбору либо ask, либо bid
        self.data[f"{new_price.value}"]["input"] = price_itself



    def number_into_indexes(self, ask_or_bid: AskOrBid): # разбиваем цену на индексы как положительные так и отрицательные, для дальнейшей работы
        self.data[f"{ask_or_bid.value}"]["positive_index"]["index"] = {str(i): char for i, char in enumerate(self.data["bid"]["input"])}
        self.data[f"{ask_or_bid.value}"]["negative_index"]["index"] = {str(-(len(self.data[f"{ask_or_bid.value}"]["input"]) - i)): char for i, char in enumerate(self.data[f"{ask_or_bid.value}"]["input"])}



    def location_of_the_point(self, ask_or_bid: AskOrBid , positive_or_negative: PositiveOrNegative):
        global function_state
        price_length = len(self.data[ask_or_bid.value][f"{positive_or_negative.value}_index"]["index"]) # Получение длины цены которую мы передали (с учетом точки)
        self.data[ask_or_bid.value]["price_length"] = price_length # Записываем длину нашей цены в json файл
        key_and_value = self.data[ask_or_bid.value][f"{positive_or_negative.value}_index"]["index"] # получаем список с индексами цены для дальнейшей обработки
        for index, value in key_and_value.items(): # цикл находит и записывает индексы, которые идут до точки и после точки
            int_index = int(index)
            if value == ".":
                before_a_point = str(int_index - 1)
                after_a_point = str(int_index + 1)
                self.data[ask_or_bid.value][f"{positive_or_negative.value}_index"]["index_before_a_point"] = before_a_point
                self.data[ask_or_bid.value][f"{positive_or_negative.value}_index"]["index_after_a_point"] = after_a_point
        found_dot = False
        count_after = 0 # цикл записывает количество символов до точки и после нее
        for count, (index, value) in enumerate(key_and_value.items(), start=0):
            if value == ".":
                count_str = str(count)
                self.data[ask_or_bid.value]["before_the_dot"] = count_str
                found_dot = True
            if found_dot:
                count_after += 1
                self.data[ask_or_bid.value]["after_the_dot"] = str(count_after - 1)
        function_state = TrackingTheFunction.EXECUTED # отмечаем то что функция была выполнена, потому что без этих данных работа других функций будет ограничена и вызывать проблемы




    def price_without_point(self, ask_or_bid: AskOrBid , positive_or_negative: PositiveOrNegative):
        global function_state
        if function_state == TrackingTheFunction.NOT_EXECUTED:
            print("функция не была выполнена")
        else:
            new_indexes = self.data[ask_or_bid.value][f"{positive_or_negative.value}_index"]["index"]
            replace_dict = {}
            for index , value in new_indexes.items():
                if value != ".":
                    index = int(index)
                    index -= 1
                    index = str(index)
                    replace_dict.update({index: value})
                else:
                    continue
            self.data[ask_or_bid.value][f"{positive_or_negative.value}_index"]["index"] = replace_dict


    def finally_price_bid(self):
        price_indexes = self.data["bid"]["negative_index"]["index"]
        dict_length = len(price_indexes)
        replace_dict = {}
        enlarged = False
        for index, value in reversed(price_indexes.items()):
            if value == "9" and index != f"-{dict_length}":
                value = "0"
                replace_dict.update({index: value})
            elif value == "9" and index == f"-{dict_length}":
                value = "0"
                replace_dict.update({index: value})
                new_index = str(dict_length + 1)
                new_item_dict = {f"-{new_index}": "1"}
                print(new_item_dict)
                replace_dict.update(new_item_dict)
            elif not enlarged:
                value = int(value)
                value += 1
                replace_dict.update({index: value})
                enlarged = True
            else:
                replace_dict.update({index: value})
        result = {str(key): str(value) for key, value in reversed(replace_dict.items())}
        self.data["bid"]["change_price"]["negative_indexes"]["index"] = result


    def finally_price_ask(self):
        price_indexes = self.data["ask"]["negative_index"]["index"]
        dict_length = str(len(price_indexes))
        dict_length = f"-{dict_length}" #добавили эту строку для того чтобы, понять какой символ будет самым последним в проверке
        replace_dict = {}
        enlarged = False #проверяем уменьшили ли мы число
        for index, value in reversed(price_indexes.items()):
            if value == "0" and not enlarged: # если значение равно 0 и если мы не уменьшаем число
                value = "9"
                replace_dict.update({index: value})

            elif value != "0" and not enlarged and value != "1":
                value = int(value)
                value -= 1
                value = str(value)
                replace_dict.update({index: value})
                enlarged = True

            elif value != "0" and not enlarged and value == "1" and index == dict_length:
                continue

            elif value != "0" and not enlarged and value == "1" and index != dict_length:
                value = int(value)
                value -= 1
                value = str(value)
                replace_dict.update({index: value})
                enlarged = True

            elif index != dict_length:
                replace_dict.update({index: value})

        result = {str(key): str(value) for key, value in reversed(replace_dict.items())}
        self.data["ask"]["change_price"]["negative_indexes"]["index"] = result

    def parsed_json(self, to_the_pass):
        data = self.data  # Начинаем с исходных данных
        for key in to_the_pass:  # Проходим по всем ключам в пути
            if isinstance(data, dict) and key in data:  # Проверяем, существует ли ключ
                data = data[key]  # Переходим на следующий уровень
            else:
                print("Я не нашел ключ:", key)
                return None  # Если ключ не найден, возвращаем None
        return data  # Возвращаем конечное значение после всех итераций
    def get_data(self):
        return self.data


json_data = JsonDataPrice('{"money":"","difference":"","bid":{"input":"","input_not_a_point":"","positive_index":{"index":{},"index_before_a_point":"","index_after_a_point":""},"negative_index": {"index":{},"index_before_a_point":"","index_after_a_point":""},"price_length": "","before_the_dot": "","after_the_dot": "", "change_not_a_point":"","change_with_a_point_after":"", "change_price": {"positive_indexes": {"index": {}} ,"negative_indexes": {"index": {}} ,"before_the_dot_and_after_change": "","after_the_dot_and_after_change": "", "price_length": ""}},"ask":{"input":"","input_not_a_point":"","positive_index":{"index":{},"index_before_a_point":"","index_after_a_point":""},"negative_index": {"index":{},"index_before_a_point":"","index_after_a_point":""},"price_length": "","before_the_dot": "","after_the_dot": "", "change_not_a_point":"","change_with_a_point_after":"", "change_price": {"positive_indexes": {"index": {}} ,"negative_indexes": {"index": {}} ,"before_the_dot_and_after_change": "","after_the_dot_and_after_change": "", "price_length": ""}}}')
json_data.update_price(AskOrBid.BID, "67544.79")
json_data.update_price(AskOrBid.ASK, "11000.0000")
json_data.number_into_indexes(AskOrBid.BID)
json_data.number_into_indexes(AskOrBid.ASK)
json_data.location_of_the_point(AskOrBid.BID, PositiveOrNegative.POSITIVE)
json_data.location_of_the_point(AskOrBid.BID, PositiveOrNegative.NEGATIVE)
json_data.location_of_the_point(AskOrBid.ASK, PositiveOrNegative.POSITIVE)
json_data.location_of_the_point(AskOrBid.ASK, PositiveOrNegative.NEGATIVE)
json_data.price_without_point(AskOrBid.BID, PositiveOrNegative.POSITIVE)
json_data.price_without_point(AskOrBid.BID, PositiveOrNegative.NEGATIVE)
json_data.price_without_point(AskOrBid.ASK, PositiveOrNegative.POSITIVE)
json_data.price_without_point(AskOrBid.ASK, PositiveOrNegative.NEGATIVE)
path = "ask","change_price","negative_indexes","index"
json_data.parsed_json(path)
json_data.finally_price_bid()
json_data.finally_price_ask()
print(json_data.parsed_json(path))
print(json_data.get_data())