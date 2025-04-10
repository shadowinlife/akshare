import functools

from akshare import g_disk_cache_enabled, g_disk_cache


def disk_cache(
        table_name: str,
        pk_cols: list,
        input_date_params: dict,
        date_col_map: dict,
        date_format='%Y%m%d'  # 日期格式化格式
):
    """
    缓存装饰器.用于将API的返回结构化为Pandas DataFrame,并存储到本地SQLite数据库中.
    适用的API需要满足以下条件:
        1. 返回数据为Pandas DataFrame
        2. DataFrame必须包含日期列,日期列的格式需要能够被date_format参数解析
        3. DataFrame必须包含主键列
        4. 每个trade_date只能对应一行数据
        5. 由于交易日历接口只适用于A股, 所以只对A股相关的交易数据构成缓存能力

    :param table_name: 存储表名
    :param pk_cols: Primary Key 列, 例如 ['股票代码', '交易日期']
    :param input_date_params: 标记Func中日期参数的名称
        如果是范围日期, 输入格式为 {'start_date_param': 'start_date', 'end_date_param': 'end_date'}.
        如果是单个日期, 输入格式为 {'date_param': 'date'}
    :param date_col_map: 从日期参数到DataFrame中的日期列的映射关系
        如果是范围日期, 输入格式为 {'start_date_param': 'start_date', 'end_date_param': 'end_date'}.
        如果是单个日期, 输入格式为 {'date_param': 'date'}
    :param date_format: 日期格式化格式
    :return: Pandas DataFrame
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 通过global变量判断是否走缓存
            if not g_disk_cache_enabled:
                df = func(*args, **kwargs)
                return df
            else:
                cached_df, hit_cache = g_disk_cache.try_fetch(
                    table_name=table_name,
                    pk_cols=pk_cols,
                    input_date_params=input_date_params,
                    date_col_map=date_col_map,
                    date_format=date_format,
                )
                if hit_cache:
                    return cached_df
                else:
                    df = func(*args, **kwargs)
                    # 从args中获取PK列对应的值
                    pk_values = []
                    for pk_col in pk_cols:
                        if pk_col in kwargs:
                            pk_values.append(kwargs[pk_col])
                        else:
                            raise ValueError(f"Primary key column {pk_col} not found in kwargs.")
                    g_disk_cache.try_async_store(
                        table_name=table_name,
                        pk_cols=pk_cols,
                        input_date_params=input_date_params,
                        output_date_col=output_date_col,
                        date_format=date_format,
                        df=df,
                    )
                    return df

        return wrapper
    return decorator


