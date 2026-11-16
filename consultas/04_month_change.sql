WITH monthly AS (
            SELECT CAST(date_trunc('month',o.ordered_at) AS DATE) AS month,
                   SUM(i.quantity * i.unit_price_cents - i.discount_cents) AS revenue_cents
            FROM orders o JOIN items i ON i.order_id=o.id
            WHERE o.status='completed' GROUP BY 1
        )
        SELECT month,revenue_cents,
               revenue_cents-LAG(revenue_cents) OVER (ORDER BY month) AS change_cents
        FROM monthly ORDER BY month;
