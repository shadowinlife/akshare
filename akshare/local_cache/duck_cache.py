import duckdb
import functools
import pandas as pd
from datetime import datetime


def duck_cache(
        api_name: str,
        input_date_params: dict,
        output_date_col: str,
        date_format='%Y%m%d'  # 日期格式化格式
):
    """
    支持范围日期缓存的装饰器

    Args:
        api_name: API名称
        input_date_params: 日期参数描述:
            - type: 'single'或'range'
            - 对于'single': {'param': 'date_param_name'}
            - 对于'range': {'start_param': 'start_name', 'end_param': 'end_name'}
        output_date_col: 输出DataFrame中的日期列名
        date_format: 输入参数的日期格式
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 提取日期参数
            if input_date_params['type'] == 'single':
                date_param = input_date_params['param']
                date_str = kwargs[date_param]
                start_date = end_date = datetime.strptime(date_str, date_format).date()
            elif input_date_params['type'] == 'range':
                start_param = input_date_params['start_param']
                end_param = input_date_params['end_param']

                start_str = kwargs[start_param]
                end_str = kwargs[end_param]

                start_date = datetime.strptime(start_str, date_format).date()
                end_date = datetime.strptime(end_str, date_format).date()
            else:
                raise ValueError("Invalid date type in input_date_params")

            # 建立DuckDB连接
            conn = duckdb.connect(database='cache.duckdb', read_only=False)
            table_name = f"cache_{api_name}"

            # 表结构处理
            def create_table(df):
                conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df LIMIT 0")
                # 设置主键
                conn.execute(f"ALTER TABLE {table_name} ADD PRIMARY KEY ({output_date_col})")

            # 缓存查询
            query = f"""
                SELECT * FROM {table_name}
                WHERE {output_date_col} BETWEEN '{start_date}' AND '{end_date}'
            """
            cached_df = conn.execute(query).fetchdf()

            # 缓存命中检测
            if not cached_df.empty:
                cached_dates = pd.to_datetime(cached_df[output_date_col]).dt.date
                all_dates = pd.date_range(start=start_date, end=end_date).date

                # 计算缺失日期
                missing_dates = all_dates[~all_dates.isin(cached_dates)]
                if missing_dates.empty:
                    print(f"Cache hit for {api_name} from {start_date} to {end_date}")
                    return cached_df
                else:
                    print(f"Partial cache hit, fetching missing dates: {missing_dates}")

            # 缓存未命中或部分命中时调用API
            result_df = func(*args, **kwargs)

            # 确保输出日期列是日期类型
            result_df[output_date_col] = pd.to_datetime(result_df[output_date_col]).dt.date

            # 表不存在则创建
            if not conn.execute(f"SELECT * FROM {table_name}").success:
                create_table(result_df)

            # 数据合并与缓存更新
            try:
                # 尝试UPSERT操作（DuckDB支持）
                conn.execute(f"""
                    INSERT INTO {table_name} 
                    SELECT * FROM result_df
                    ON CONFLICT ({output_date_col})
                    DO UPDATE SET 
                        {', '.join([f"{col}=EXCLUDED.{col}" for col in result_df.columns
                                    if col != output_date_col])}
                """)
            except:
                # 回退方案：先删除旧数据再插入
                conn.execute(f"""
                    DELETE FROM {table_name}
                    WHERE {output_date_col} BETWEEN '{start_date}' AND '{end_date}'
                """)
                conn.execute(f"INSERT INTO {table_name} SELECT * FROM result_df")

            return result_df

        return wrapper

    return decorator
