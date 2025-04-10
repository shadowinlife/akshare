import os
import sqlite3

import pandas as pd

from akshare import tool_trade_date_hist_sina


class DiskCache:
    """
    Local Cache是依赖Python内置的SQLite3模块实现的一个简单的本地缓存系s统。
    """
    def __init__(self):
        if os.environ.get("AKSHARE_LOCAL_CACHE_DIR") is None:
            self.is_active = False
        else:
            cache_dir = os.environ.get("AKSHARE_LOCAL_CACHE_DIR")
            # 测试缓存目录是否具有读写权限
            if os.access(cache_dir, os.W_OK):
                # 创建/读取SQLite数据库
                if not cache_dir.endswith("/"):
                    cache_dir += "/"
                self.db_file = cache_dir + "akshare_cache.db"
                try:
                    self.con = sqlite3.connect(self.db_file)
                    self.is_active = True
                    # 获取到A股的交易日历
                    self.trade_date = tool_trade_date_hist_sina()
                except sqlite3.Error as e:
                    print(f"SQLite error: {e}")
                    self.is_active = False
            else:
                print(f"Cache directory {cache_dir} is not writable.")
                self.is_active = False

    def is_active(self):
        """
        检查缓存是否可以用
        """
        return self.is_active

    def try_fetch(self,
                  kwargs: dict,
                  table_name: str,
                  pk_cols: list,
                  input_date_params: dict,
                  date_col_name: str,
                  date_format='%Y%m%d',
                  ):
        """
        从SQLite数据库中读取数据

        :param kwargs: API入参的KEY值对
        :param table_name: 存储表名
        :param pk_cols: Primary Key 列, 例如 ['股票代码', '交易日期']
        :param input_date_params: 标记Func中日期参数的名称
            如果是范围日期, 输入格式为 {'start_date_param': 'start_date', 'end_date_param': 'end_date'}.
            如果是单个日期, 输入格式为 {'date_param': 'date'}
        :param date_col_name: 日期列的名称
        :param date_format: 日期格式化
        :return: DataFrame, bool
        """
        if not self.is_active:
            return None, False
        try:
            # 从参数中获取过滤条件
            pk_filter = self._get_pk_filter(pk_cols, kwargs)
            date_filter = self._get_date_filter(input_date_params, kwargs, date_format)
            # 构建SQL语句
            _data_sql, valid_sql = self._build_sql(table_name, pk_filter, date_filter, date_col_name)
            # 执行SQL语句获取数据
            cursor = self.con.cursor()
            cursor.execute(_data_sql)
            rows = cursor.fetchall()
            # 执行SQL语句获取到这个表到DataFrame的映射关系
            _meta_sql = f"""
                SELECT i, col_name, pd_name, pd_type 
                FROM table_mapping WHERE table_name = {table_name} order by i
            """
            cursor.execute(_meta_sql)
            columns = cursor.fetchall()
            pd = self._build_pd(rows, columns)
            return pd, True
        except Exception as e:
            print(f"Fetch cache data error: {e}")
            return None, False

    def try_async_store(self, key, value):
        """Set the value in the cache by key."""
        self.cache[key] = value

    def destroy_cache(self):
        """
        删除数据库文件
        """
        try:
            os.remove(self.db_file)
        except FileNotFoundError:
            print(f"Cache file {self.db_file} not found.Delete local db failed.")

    def _build_pd(self, rows, columns):
        """
        将数据转换为DataFrame
        :param rows: 数据行
        :param columns: Pandas的列名和属性. 结构如下:
            - i: 列号, 从0开始. 0号列总是索引列
            - col_name: 表中的列名
            - pd_name: 对应的Pandas列名
            - pd_type: 对应的Pandas列的数值类型. None代表PD中没有这个列
        :return: DataFrame
        """
        # 基于columns的值来构建一个空的DataFrame
        columns = [col[2] for col in columns if col[3] is not None]
        df = pd.DataFrame(columns=columns)
        # 将数据行转换为DataFrame
        for row in rows:
            # 处理每一行数据
            row_dict = {}
            for i, col in enumerate(columns):
                if col[3] is not None:
                    row_dict[col[2]] = row[i]
            df = df.append(row_dict, ignore_index=True)
        # 针对DataFrame中的列做类型转换
        for col in columns:
            if col[3] is not None:
                if col[3] == "int":
                    df[col[2]] = df[col[2]].astype(int)
                elif col[3] == "float":
                    df[col[2]] = df[col[2]].astype(float)
                elif col[3] == "str":
                    df[col[2]] = df[col[2]].astype(str)
                elif col[3] == "datetime":
                    df[col[2]] = pd.to_datetime(df[col[2]], format="%Y%m%d")
                elif col[3] == "date":
                    df[col[2]] = pd.to_datetime(df[col[2]], format="%Y%m%d").dt.date
                elif col[3] == "bool":
                    df[col[2]] = df[col[2]].astype(bool)
        # 处理索引列
        index_col = columns[0][2]
        if index_col in df.columns:
            df.set_index(index_col, inplace=True)
        # 返回DataFrame
        return df

    def _build_sql(self, table_name: str, pk_filter: dict, date_filter: list, date_col_name: str):
        """
        利用过滤信息来构建SQL语句
        :param table_name: 表名
        :param pk_filter: 主键过滤条件, 值为空代表不需要过滤. 例如 {'symbol': '000001', 'adjust': None, 'period': 'daily'}
        :param date_filter: 日期过滤条件, 有两种情况:
            1. 单日期: ['2025-01-01']
            2. 日期范围: ['2025-01-01', '2025-01-31']
        :param date_col_name: 日期列的名称
        :return:
        """
        # 构筑验证 时间范围 内数据是否存在的SQL
        if len(date_filter) == 1:
            valid_sql = f"SELECT count(*) FROM {table_name} WHERE {date_col_name} = '{date_filter[0]}'"
        else:
            valid_sql = f"""SELECT count(*) FROM {table_name} WHERE {date_col_name} >= '{date_filter[0]}' 
                        AND {date_col_name} <= '{date_filter[1]}'"""

        # 构筑取数据的SQL
        _data_sql = f"SELECT * FROM {table_name} WHERE"
        for key, value in pk_filter.items():
            if value is not None:
                _data_sql += f" {key} = '{value}' AND "
        if len(date_filter) == 1:
            _data_sql += f"{date_col_name} = '{date_filter[0]}'"
        else:
            _data_sql += f"{date_col_name} >= '{date_filter[0]}' AND {date_col_name} <= '{date_filter[1]}'"
        return _data_sql


    def _get_date_filter(self, input_date_params: dict, kwargs: dict, date_format, col_date_name: str):
        """
        从kwargs中获取日期参数的值

        :param input_date_params: 输入日期参数
        :param kwargs: 参数字典
        :return: 日期参数的值
        """
        date_filter = []
        # API设计上是一个单日的日期
        if  'date_param' in input_date_params:
            # 在所有参数中找到这个日期的值
            date_param = input_date_params['date_param']
            if date_param in kwargs:
                value = kwargs[date_param].strftime(date_format)
                date_filter.append(value)

        # API设计上是一个范围日期
        else:
            # 找到范围的start和end日期
            start_date_param = input_date_params['start_date_param']
            end_date_param = input_date_params['end_date_param']
            # 处理日期范围
            if start_date_param in kwargs:
                date_filter.append(kwargs[start_date_param].strftime(date_format))
            else:
                raise ValueError(f"Start date parameter {start_date_param} not found in kwargs.")
            if end_date_param in kwargs:
                date_filter.append(kwargs[end_date_param].strftime(date_format))
            else:
                raise ValueError(f"End date parameter {end_date_param} not found in kwargs.")
        return date_filter

    def _get_pk_filter(self, pk_cols: list, kwargs):
        """
        基于主键列的设定, 从kwargs中获取主键列的值, 并返回一个字典.
        这个字典用来构筑SQL语句的WHERE条件.

        :param pk_cols: 主键列的参数名
        :param kwargs: 参数字典
        :return: 主键列键值对
        """
        pk_dict = {}
        for pk_col in pk_cols:
            if pk_col in kwargs:
                pk_dict[pk_col] = kwargs[pk_col]
            else:
                pk_dict[pk_col] = None
        return pk_dict