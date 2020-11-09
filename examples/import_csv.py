from vnpy.trader.constant import (Exchange, Interval)
import pandas as pd
from vnpy.trader.database import database_manager
from vnpy.trader.object import (BarData,TickData)
from datetime import datetime, timedelta, timezone
import sys

# 封装函数
def move_df_to_mongodb(imported_data:pd.DataFrame,collection_name:str):
    ticks = []
    start = None
    count = 0
    utc_8 = timezone(timedelta(hours=8))
    for row in imported_data.itertuples():

        tick = TickData(
              symbol = row.symbol,
              exchange = row.exchange,
              datetime = row.datetime.replace(tzinfo=utc_8),
              #datetime = row.datetime,
              name = "TickDataName",
              volume = row.volume,
              open_interest = row.open_interest,
              turnover = row.turnover,
              last_price = row.last_price,
              last_volume = row.last_volume,
              last_amount = row.last_amount,
              limit_up = row.limit_up,
              limit_down = row.limit_down,
              open_price = row.open_price,
              high_price = row.high_price,
              low_price = row.low_price,
              pre_close = row.pre_close,
              bid_price_1 = row.bid_price_1,
              bid_price_2 = row.bid_price_2,
              bid_price_3 = row.bid_price_3,
              bid_price_4 = row.bid_price_4,
              bid_price_5 = row.bid_price_5,
              ask_price_1 = row.ask_price_1,
              ask_price_2 = row.ask_price_2,
              ask_price_3 = row.ask_price_3,
              ask_price_4 = row.ask_price_4,
              ask_price_5 = row.ask_price_5,
              bid_volume_1 = row.bid_volume_1,
              bid_volume_2 = row.bid_volume_2,
              bid_volume_3 = row.bid_volume_3,
              bid_volume_4 = row.bid_volume_4,
              bid_volume_5 = row.bid_volume_5,
              ask_volume_1 = row.ask_volume_1,
              ask_volume_2 = row.ask_volume_2,
              ask_volume_3 = row.ask_volume_3,
              ask_volume_4 = row.ask_volume_4,
              ask_volume_5 = row.ask_volume_5,
              gateway_name="DB",
        )
        ticks.append(tick)

        # do some statistics
        count += 1
        if not start:
            start = tick.datetime
    end = tick.datetime

    # insert into database
    database_manager.save_tick_data(ticks, collection_name)
    print(f'Insert Tick: {count} from {start} - {end}')

if __name__ == "__main__":
    #imported_data = pd.read_csv('D:\Study\数据\PoboForVnpy\cu7777\cu7777_20200907-20200911.csv',encoding='utf-8')
    #imported_data = pd.read_csv('D:\Study\数据\PoboForVnpy\cu6666\cu6666_20200907-20200911.csv',encoding='utf-8')
    #imported_data = pd.read_csv('D:/Study/数据/PoboForVnpy/al6666/al6666_20200907-20200911.csv',encoding='utf-8')
    #imported_data = pd.read_csv('D:/Study/数据/PoboForVnpy/al7777/al7777_20200907-20200911.csv',encoding='utf-8')
    
    sys_collection_name = sys.argv[1]
    sys_data_path = sys.argv[2]
    
    imported_data = pd.read_csv(sys_data_path,encoding='utf-8')
    
    
    # 将csv文件中 `市场代码`的 SC 替换成 Exchange.SHFE SHFE
    imported_data['exchange'] = Exchange.SHFE
    # 明确需要是float数据类型的列
    float_columns = ['volume','open_interest','last_price','last_volume','limit_up','limit_down','open_price','high_price','low_price','pre_close','bid_price_1','bid_price_2','bid_price_3','bid_price_4','bid_price_5','ask_price_1','ask_price_2','ask_price_3','ask_price_4','ask_price_5','bid_volume_1','bid_volume_2','bid_volume_3','bid_volume_4','bid_volume_5','ask_volume_1','ask_volume_2','ask_volume_3','ask_volume_4','ask_volume_5']
    for col in float_columns:
      imported_data[col] = imported_data[col].astype('float')
    # 明确时间戳的格式
    # %Y-%m-%d %H:%M:%S.%f 代表着你的csv数据中的时间戳必须是 2020-05-01 08:32:30.500000 格式
    datetime_format = '%Y-%m-%d %H:%M:%S.%f'
    imported_data['datetime'] = pd.to_datetime(imported_data['datetime'],format=datetime_format)


    #!!!!!!!!!!!    记得改名
    #move_df_to_mongodb(imported_data,'cu7777')
    #move_df_to_mongodb(imported_data,'cu6666')
    #move_df_to_mongodb(imported_data,'al6666')
    #move_df_to_mongodb(imported_data,'al7777')
    
    move_df_to_mongodb(imported_data, sys_collection_name)
