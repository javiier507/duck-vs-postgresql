SELECT c.id, c.region, SUM(i.quantity * i.unit_price_cents - i.discount_cents) AS revenue_cents
        FROM customers c JOIN orders o ON o.customer_id=c.id
        JOIN items i ON i.order_id=o.id WHERE o.status='completed'
        GROUP BY c.id,c.region ORDER BY revenue_cents DESC,c.id LIMIT 20;
