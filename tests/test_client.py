from garmin_sync.client import GarminReader


class PagedApi:
    def __init__(self):
        self.starts = []

    def get_activities(self, start, limit):
        self.starts.append(start)
        pages = {0: [{"activityId": 1}, {"activityId": 2}], 2: [{"activityId": 3}], 3: []}
        return pages[start]


def test_historical_pagination():
    api = PagedApi()
    values = list(GarminReader(api, delay=0, page_size=2).iter_all_activities())
    assert [value["activityId"] for value in values] == [1, 2, 3]
    assert api.starts == [0, 2]
