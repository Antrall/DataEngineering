"""
Этапы 5 и 6: влияние навыков на медианную зарплату и сравнение трёх регионов.
Запуск (из корня HW3): python src/analysis.py > results/analysis_output.md
"""
import common
from duckdb_sql import RAW_DATA_URL, SKILL_ALIASES_URL, connect


MIN_PAIR_VACANCIES = 100
MIN_TRIPLE_VACANCIES = 60
MIN_SINGLE_SKILL_VACANCIES = 300
MIN_REGION_SKILL_VACANCIES = 100

REGIONS = ["Москва", "Санкт-Петербург", "Новосибирск"]
RUB_PER_CURRENCY = {"RUR": 1, "USD": 90, "EUR": 100, "KZT": 0.19}
NET_SALARY_SHARE = 0.87

CREATE_VACANCIES_QUERY = f"""
CREATE TABLE vacancies AS
SELECT
    vacancy_id,
    area,
    schedule,
    key_skills,
    CASE
        WHEN salary_from <> '' AND salary_to <> ''
            THEN (CAST(salary_from AS DOUBLE) + CAST(salary_to AS DOUBLE)) / 2
        WHEN salary_from <> '' THEN CAST(salary_from AS DOUBLE)
        WHEN salary_to <> '' THEN CAST(salary_to AS DOUBLE)
    END
    * CASE currency
        WHEN 'RUR' THEN {RUB_PER_CURRENCY['RUR']}
        WHEN 'USD' THEN {RUB_PER_CURRENCY['USD']}
        WHEN 'EUR' THEN {RUB_PER_CURRENCY['EUR']}
        WHEN 'KZT' THEN {RUB_PER_CURRENCY['KZT']}
    END
    * CASE WHEN gross = 'true' THEN {NET_SALARY_SHARE} ELSE 1 END AS salary
FROM read_csv('{RAW_DATA_URL}', header = true, all_varchar = true)
WHERE role = '{common.VARIANT_ROLE}'
"""

CREATE_ALIASES_QUERY = f"""
CREATE TABLE skill_aliases AS
SELECT alias, skill
FROM read_csv('{SKILL_ALIASES_URL}', header = true, all_varchar = true)
"""

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

CREATE_SALARIED_VACANCIES_QUERY = """
CREATE TABLE salaried_vacancies AS
SELECT vacancy_id, area, schedule, salary
FROM vacancies
WHERE salary IS NOT NULL
"""

CREATE_SALARIED_SKILLS_QUERY = """
CREATE TABLE salaried_skills AS
SELECT vacancy_skills.vacancy_id, vacancy_skills.skill
FROM vacancy_skills
JOIN salaried_vacancies USING (vacancy_id)
"""

CREATE_SKILL_STATS_QUERY = """
CREATE TABLE skill_stats AS
SELECT
    salaried_skills.skill,
    count(*) AS vacancy_count,
    median(salaried_vacancies.salary) AS median_salary
FROM salaried_skills
JOIN salaried_vacancies USING (vacancy_id)
GROUP BY salaried_skills.skill
"""

CREATE_PAIR_STATS_QUERY = """
CREATE TABLE pair_stats AS
SELECT
    first_skill.skill AS first_skill,
    second_skill.skill AS second_skill,
    count(*) AS vacancy_count,
    median(salaried_vacancies.salary) AS median_salary
FROM salaried_skills AS first_skill
JOIN salaried_skills AS second_skill
    ON first_skill.vacancy_id = second_skill.vacancy_id
    AND first_skill.skill < second_skill.skill
JOIN salaried_vacancies ON salaried_vacancies.vacancy_id = first_skill.vacancy_id
GROUP BY 1, 2
"""

CREATE_TRIPLE_STATS_QUERY = """
CREATE TABLE triple_stats AS
SELECT
    first_skill.skill AS first_skill,
    second_skill.skill AS second_skill,
    third_skill.skill AS third_skill,
    count(*) AS vacancy_count,
    median(salaried_vacancies.salary) AS median_salary
FROM salaried_skills AS first_skill
JOIN salaried_skills AS second_skill
    ON first_skill.vacancy_id = second_skill.vacancy_id
    AND first_skill.skill < second_skill.skill
JOIN salaried_skills AS third_skill
    ON first_skill.vacancy_id = third_skill.vacancy_id
    AND second_skill.skill < third_skill.skill
JOIN salaried_vacancies ON salaried_vacancies.vacancy_id = first_skill.vacancy_id
GROUP BY 1, 2, 3
HAVING count(*) >= {min_triple_vacancies}
"""

CREATE_PAIR_EFFECT_QUERY = """
CREATE TABLE pair_effect AS
SELECT
    pair_stats.first_skill,
    pair_stats.second_skill,
    pair_stats.vacancy_count,
    pair_stats.median_salary,
    CASE WHEN first_stats.vacancy_count >= second_stats.vacancy_count
        THEN pair_stats.first_skill ELSE pair_stats.second_skill END AS base_skill,
    CASE WHEN first_stats.vacancy_count >= second_stats.vacancy_count
        THEN first_stats.median_salary ELSE second_stats.median_salary END AS base_median_salary,
    pair_stats.median_salary - CASE WHEN first_stats.vacancy_count >= second_stats.vacancy_count
        THEN first_stats.median_salary ELSE second_stats.median_salary END AS delta_to_base,
    pair_stats.median_salary - (SELECT median(salary) FROM salaried_vacancies) AS delta_to_overall
FROM pair_stats
JOIN skill_stats AS first_stats ON first_stats.skill = pair_stats.first_skill
JOIN skill_stats AS second_stats ON second_stats.skill = pair_stats.second_skill
WHERE pair_stats.vacancy_count >= {min_pair_vacancies}
"""

CREATE_TRIPLE_EFFECT_QUERY = """
CREATE TABLE triple_effect AS
WITH with_frequencies AS (
    SELECT
        triple_stats.*,
        first_stats.vacancy_count AS first_count,
        second_stats.vacancy_count AS second_count,
        third_stats.vacancy_count AS third_count
    FROM triple_stats
    JOIN skill_stats AS first_stats ON first_stats.skill = triple_stats.first_skill
    JOIN skill_stats AS second_stats ON second_stats.skill = triple_stats.second_skill
    JOIN skill_stats AS third_stats ON third_stats.skill = triple_stats.third_skill
),
with_rarest AS (
    SELECT
        *,
        CASE
            WHEN first_count <= second_count AND first_count <= third_count THEN 1
            WHEN second_count <= third_count THEN 2
            ELSE 3
        END AS rarest_position
    FROM with_frequencies
),
with_base_pair AS (
    SELECT
        *,
        CASE rarest_position WHEN 1 THEN second_skill ELSE first_skill END AS base_first_skill,
        CASE rarest_position WHEN 3 THEN second_skill ELSE third_skill END AS base_second_skill,
        CASE rarest_position WHEN 1 THEN first_skill WHEN 2 THEN second_skill ELSE third_skill END AS added_skill
    FROM with_rarest
)
SELECT
    with_base_pair.first_skill,
    with_base_pair.second_skill,
    with_base_pair.third_skill,
    with_base_pair.vacancy_count,
    with_base_pair.median_salary,
    with_base_pair.added_skill,
    with_base_pair.base_first_skill || ' + ' || with_base_pair.base_second_skill AS base_pair,
    pair_stats.median_salary AS base_median_salary,
    with_base_pair.median_salary - pair_stats.median_salary AS delta_to_base,
    with_base_pair.median_salary - (SELECT median(salary) FROM salaried_vacancies) AS delta_to_overall
FROM with_base_pair
JOIN pair_stats
    ON pair_stats.first_skill = with_base_pair.base_first_skill
    AND pair_stats.second_skill = with_base_pair.base_second_skill
"""


def format_number(value):
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.0f}"
        return f"{value:.2f}".rstrip("0").rstrip(".")

    return str(value)


def print_query_result(connection, title, query):
    cursor = connection.execute(query)
    column_names = [column[0] for column in cursor.description]

    print(f"\n## {title}")
    print("| " + " | ".join(column_names) + " |")
    print("|" + "---|" * len(column_names))
    for row in cursor.fetchall():
        print("| " + " | ".join(format_number(value) for value in row) + " |")


def save_query_result(connection, client, key, query):
    cursor = connection.execute(query)
    header = [column[0] for column in cursor.description]
    rows = [
        [round(value, 1) if isinstance(value, float) else value for value in row]
        for row in cursor.fetchall()
    ]

    common.write_csv_object(client, key, header, rows)


def show_and_save(connection, client, title, key, query):
    print_query_result(connection, title, query)
    save_query_result(connection, client, key, query)


def analyze_salary_effects(connection, client):
    """
    Этап 5: пары и тройки навыков, которые сильнее всего повышают и понижают медианную зарплату.
    """
    effect_tables = [
        ("pair_effect", "first_skill || ' + ' || second_skill AS pair", MIN_PAIR_VACANCIES),
        ("triple_effect", "first_skill || ' + ' || second_skill || ' + ' || third_skill AS triple", MIN_TRIPLE_VACANCIES),
    ]
    base_column = {
        "pair_effect": "base_skill",
        "triple_effect": "base_pair",
    }

    for table_name, label_expression, min_vacancies in effect_tables:
        for direction, sort_order in (("raise", "DESC"), ("lower", "ASC")):
            query = f"""
            SELECT
                {label_expression},
                vacancy_count,
                median_salary,
                {base_column[table_name]} AS base,
                base_median_salary,
                delta_to_base,
                delta_to_overall
            FROM {table_name}
            ORDER BY delta_to_base {sort_order}, 1
            LIMIT 10
            """
            suffix = "up" if direction == "raise" else "down"
            show_and_save(
                connection,
                client,
                f"{table_name}: top 10 that {direction} the salary (vacancies >= {min_vacancies})",
                f"results/analysis/{table_name}_{suffix}.csv",
                query,
            )

    query = f"""
    SELECT
        skill,
        vacancy_count,
        median_salary,
        median_salary - (SELECT median(salary) FROM salaried_vacancies) AS delta_to_overall
    FROM skill_stats
    WHERE vacancy_count >= {MIN_SINGLE_SKILL_VACANCIES}
    ORDER BY median_salary DESC, skill
    """
    show_and_save(
        connection,
        client,
        f"single skills (vacancies >= {MIN_SINGLE_SKILL_VACANCIES}), by median",
        "results/analysis/skill_median.csv",
        query,
    )


def build_region_skills_query(regions_sql):
    return f"""
    WITH region_skills AS (
        SELECT vacancy_skills.skill, vacancies.area, vacancies.salary, vacancy_skills.vacancy_id
        FROM vacancy_skills
        JOIN vacancies USING (vacancy_id)
    ),
    total AS (SELECT count(*) AS vacancy_count FROM vacancies),
    region_totals AS (SELECT area, count(*) AS vacancy_count FROM vacancies GROUP BY area),
    skill_totals AS (SELECT skill, count(*) AS vacancy_count FROM vacancy_skills GROUP BY skill)
    SELECT
        region_skills.area AS region,
        region_skills.skill,
        count(*) AS vacancies,
        round(100.0 * count(*) / any_value(region_totals.vacancy_count), 1) AS pct_region,
        round(
            (count(*) * 1.0 / any_value(region_totals.vacancy_count))
            / (any_value(skill_totals.vacancy_count) * 1.0 / any_value(total.vacancy_count)),
            2
        ) AS demand_index,
        median(region_skills.salary) AS median_salary
    FROM region_skills
    JOIN region_totals ON region_totals.area = region_skills.area
    JOIN skill_totals ON skill_totals.skill = region_skills.skill,
    total
    WHERE region_skills.area IN ({regions_sql})
    GROUP BY region_skills.area, region_skills.skill
    """


def analyze_regions(connection, client):
    """
    Этап 6: сравнение регионов по зарплатам и востребованности навыков.
    """
    regions_sql = ", ".join(f"'{region}'" for region in REGIONS)

    query = f"""
    SELECT
        area AS region,
        count(*) AS vacancies,
        count(salary) AS with_salary,
        round(100.0 * count(salary) / count(*), 1) AS pct_salary,
        median(salary) AS median,
        quantile_cont(salary, 0.25) AS p25,
        quantile_cont(salary, 0.75) AS p75,
        round(100.0 * sum(CASE WHEN schedule = 'remote' THEN 1 ELSE 0 END) / count(*), 1) AS pct_remote
    FROM vacancies
    WHERE area IN ({regions_sql})
    GROUP BY area
    ORDER BY vacancies DESC
    """
    show_and_save(connection, client, "region summary", "results/analysis/regions_summary.csv", query)

    total_vacancies = connection.execute("SELECT count(*) FROM vacancies").fetchone()[0]
    print("\ntotal variant vacancies:", total_vacancies)

    region_skills_query = build_region_skills_query(regions_sql)
    for region in REGIONS:
        top_query = f"""
        SELECT skill, vacancies, pct_region, demand_index, median_salary
        FROM ({region_skills_query})
        WHERE region = '{region}'
        ORDER BY vacancies DESC, skill
        LIMIT 10
        """
        show_and_save(
            connection,
            client,
            f"{region}: top 10 skills by vacancy count",
            f"results/analysis/region_top_{region}.csv",
            top_query,
        )

        distinctive_query = f"""
        SELECT skill, vacancies, pct_region, demand_index, median_salary
        FROM ({region_skills_query})
        WHERE region = '{region}' AND vacancies >= {MIN_REGION_SKILL_VACANCIES}
        ORDER BY demand_index DESC, skill
        LIMIT 5
        """
        show_and_save(
            connection,
            client,
            f"{region}: skills in higher demand than average (demand index, vacancies >= {MIN_REGION_SKILL_VACANCIES})",
            f"results/analysis/region_distinct_{region}.csv",
            distinctive_query,
        )

    for region in REGIONS:
        pairs_query = f"""
        SELECT
            first_skill.skill || ' + ' || second_skill.skill AS pair,
            count(*) AS vacancies
        FROM vacancy_skills AS first_skill
        JOIN vacancy_skills AS second_skill
            ON first_skill.vacancy_id = second_skill.vacancy_id
            AND first_skill.skill < second_skill.skill
        JOIN vacancies ON vacancies.vacancy_id = first_skill.vacancy_id
        WHERE vacancies.area = '{region}'
        GROUP BY 1
        ORDER BY vacancies DESC, pair
        LIMIT 5
        """
        show_and_save(
            connection,
            client,
            f"{region}: top 5 pairs",
            f"results/analysis/region_pairs_{region}.csv",
            pairs_query,
        )


def main():
    connection = connect()
    client = common.create_s3_client()

    connection.execute(CREATE_VACANCIES_QUERY)
    connection.execute(CREATE_ALIASES_QUERY)
    connection.execute(CREATE_VACANCY_SKILLS_QUERY)
    connection.execute(CREATE_SALARIED_VACANCIES_QUERY)
    connection.execute(CREATE_SALARIED_SKILLS_QUERY)
    connection.execute(CREATE_SKILL_STATS_QUERY)
    connection.execute(CREATE_PAIR_STATS_QUERY)
    connection.execute(CREATE_TRIPLE_STATS_QUERY.format(min_triple_vacancies=MIN_TRIPLE_VACANCIES))
    connection.execute(CREATE_PAIR_EFFECT_QUERY.format(min_pair_vacancies=MIN_PAIR_VACANCIES))
    connection.execute(CREATE_TRIPLE_EFFECT_QUERY)

    median_salary = connection.execute("SELECT median(salary) FROM salaried_vacancies").fetchone()[0]
    print("variant vacancies:", connection.execute("SELECT count(*) FROM vacancies").fetchone()[0])
    print("with salary:", connection.execute("SELECT count(*) FROM salaried_vacancies").fetchone()[0])
    print(f"median over all vacancies with salary (net rubles): {median_salary:.0f}")

    analyze_salary_effects(connection, client)
    analyze_regions(connection, client)


if __name__ == "__main__":
    main()
