SELECT o.id,o.ordered_at,o.status,i.id,i.product_id,i.quantity,
               i.unit_price_cents,i.discount_cents
        FROM orders o JOIN items i ON i.order_id=o.id
        WHERE o.id=42 ORDER BY i.id;
