"""
Те же частоты навыков, пар и троек навыков, но SQL-запросом в DuckDB. Данные читаются из S3.
Запуск (из корня HW3): python src/duckdb_sql.py
"""
import time
import duckdb
import s3fs
import common


RAW_DATA_URL = f"s3://{common.BUCKET_NAME}/{common.RAW_DATA_KEY}"
SKILL_ALIASES_URL = f"s3://{common.BUCKET_NAME}/{common.SKILL_ALIASES_KEY}"


def connect():
    filesystem = s3fs.S3FileSystem(
        key=common.ACCESS_KEY,
        secret=common.SECRET_KEY,
        use_listings_cache=False,
        client_kwargs={"endpoint_url": common.ENDPOINT_URL, "region_name": "us-east-1"},
        config_kwargs={"s3": {"addressing_style": "path"}},
    )
    connection = duckdb.connect()
    connection.register_filesystem(filesystem)

    return connection


# 1. Вакансии варианта (фильтр по колонке role)
CREATE_VACANCIES_QUERY = f"""
CREATE TABLE vacancies AS
SELECT vacancy_id, key_skills
FROM read_csv('{RAW_DATA_URL}', header = true, all_varchar = true)
WHERE role = '{common.VARIANT_ROLE}'
"""

# 2. Словарь синонимов навыков
CREATE_ALIASES_QUERY = f"""
CREATE TABLE skill_aliases AS
SELECT alias, skill
FROM read_csv('{SKILL_ALIASES_URL}', header = true, all_varchar = true)
"""

# 3. Пары (вакансия, навык)
CREATE_VACANCY_SKILLS_QUERY = """
CREATE TABLE vacancy_skills AS
SELECT DISTINCT
    raw.vacancy_id,
    COALESCE(skill_aliases.skill, raw.raw_skill) AS skill
FROM (
    SELECT vacancy_id, lower(trim(unnest(string_split(key_skills, ',')))) AS raw_skill
    FROM vacancies
) AS raw
LEFT JOIN skill_aliases ON skill_aliases.alias = raw.raw_skill
WHERE raw.raw_skill <> ''
"""

SKILLS_QUERY = """
SELECT skill, count(*) AS vacancies
FROM vacancy_skills
GROUP BY skill
ORDER BY vacancies DESC, skill
"""

PAIRS_QUERY = """
SELECT
    first_skill.skill AS skill_1,
    second_skill.skill AS skill_2,
    count(*) AS vacancies
FROM vacancy_skills AS first_skill
JOIN vacancy_skills AS second_skill
    ON first_skill.vacancy_id = second_skill.vacancy_id
    AND first_skill.skill < second_skill.skill
GROUP BY 1, 2
ORDER BY vacancies DESC, skill_1, skill_2
"""

TRIPLES_QUERY = """
SELECT
    first_skill.skill AS skill_1,
    second_skill.skill AS skill_2,
    third_skill.skill AS skill_3,
    count(*) AS vacancies
FROM vacancy_skills AS first_skill
JOIN vacancy_skills AS second_skill
    ON first_skill.vacancy_id = second_skill.vacancy_id
    AND first_skill.skill < second_skill.skill
JOIN vacancy_skills AS third_skill
    ON first_skill.vacancy_id = third_skill.vacancy_id
    AND second_skill.skill < third_skill.skill
GROUP BY 1, 2, 3
ORDER BY vacancies DESC, skill_1, skill_2, skill_3
"""

STACK_QUERIES = {
    1: SKILLS_QUERY,
    2: PAIRS_QUERY,
    3: TRIPLES_QUERY,
}


def main():
    start_time = time.time()
    connection = connect()
    client = common.create_s3_client()

    connection.execute(CREATE_VACANCIES_QUERY)
    connection.execute(CREATE_ALIASES_QUERY)
    connection.execute(CREATE_VACANCY_SKILLS_QUERY)
    vacancy_count = connection.execute("SELECT count(*) FROM vacancies").fetchone()[0]
    print("variant vacancies:", vacancy_count)

    for stack_size, query in STACK_QUERIES.items():
        cursor = connection.execute(query)
        header = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        common.write_csv_object(client, f"results/duckdb/skills_{stack_size}.csv", header, rows)
        print(f"results/duckdb/skills_{stack_size}.csv: {len(rows)} rows")

    print(f"done in {time.time() - start_time:.1f} s")


if __name__ == "__main__":
    main()
