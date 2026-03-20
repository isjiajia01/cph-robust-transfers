-- BigQuery template for delay quantiles
SELECT
  line,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(50)] AS p50_delay,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(90)] AS p90_delay,
  APPROX_QUANTILES(delay_sec, 100)[OFFSET(95)] AS p95_delay
FROM `PROJECT.DATASET.departures`
WHERE delay_sec IS NOT NULL
GROUP BY line
ORDER BY p95_delay DESC;
