import os
import sqlite3

from pandas import DataFrame


class DiskCache:
    """
    Local Cache是依赖Python内置的SQLite3模块实现的一个简单的本地缓存系统。
    """
    def __init__(self):
        if os.environ.get("AKSHARE_LOCAL_CACHE_DIR") is None:
            self.is_active = False
        else:
            cache_dir = os.environ.get("AKSHARE_LOCAL_CACHE_DIR")
            # 测试缓存目录是否具有读写权限
            if os.access(cache_dir, os.W_OK):
                self.is_active = True
                # 创建/读取SQLite数据库
                if not cache_dir.endswith("/"):
                    cache_dir += "/"
                self.db_file = cache_dir + "akshare_cache.db"
                try:
                    self.con = sqlite3.connect(self.db_file)
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
                  table_name: str,
                  pk_value_dict: list,
                  input_date_params: dict,
                  output_date_col: str,
                  date_format='%Y%m%d'):
        """
        从SQLite数据库中读取数据

        :param table_name: 表名
        :param pk_cols: 主键列
        :param input_date_params: 日期参数
        :param output_date_col: 输出日期列
        :param date_format: 日期格式
        :return: DataFrame, bool
        """
        sql: str = f"SELECT * FROM {table_name} WHERE "
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
