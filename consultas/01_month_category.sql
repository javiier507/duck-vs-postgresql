SELECT CAST(date_trunc('month', o.ordered_at) AS DATE) AS month,
               p.category, COUNT(*) AS lines, SUM(i.quantity * i.unit_price_cents - i.discount_cents) AS revenue_cents
        FROM orders o JOIN items i ON i.order_id=o.id
        JOIN products p ON p.id=i.product_id
        WHERE o.status='completed'
        GROUP BY 1,2 ORDER BY 1,2;
