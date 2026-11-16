SELECT id,ordered_at,status FROM orders
        WHERE customer_id=(SELECT customer_id FROM orders WHERE id=42)
        ORDER BY ordered_at DESC,id DESC LIMIT 50;
