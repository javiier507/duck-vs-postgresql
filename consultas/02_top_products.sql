SELECT p.id, p.name, SUM(i.quantity) AS units, SUM(i.quantity * i.unit_price_cents - i.discount_cents) AS revenue_cents
        FROM orders o JOIN items i ON i.order_id=o.id
        JOIN products p ON p.id=i.product_id
        WHERE o.status='completed'
        GROUP BY p.id,p.name ORDER BY revenue_cents DESC,p.id LIMIT 20;
