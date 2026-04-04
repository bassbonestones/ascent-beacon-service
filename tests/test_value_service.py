"""Tests for value service functions."""

import pytest
from decimal import Decimal

from app.services.value_service import (
    calculate_normalized_weights,
    redistribute_weight,
    normalize_value_weights,
)
from app.models.value import Value, ValueRevision


class TestNormalizeValueWeights:
    """Tests for the normalize_value_weights async function."""
    
    @pytest.mark.asyncio
    async def test_normalize_no_values(self, db_session, test_user):
        """No values means no changes."""
        await normalize_value_weights(db_session, test_user.id)
        # Should complete without error
    
    @pytest.mark.asyncio
    async def test_normalize_single_value(self, db_session, test_user):
        """Single value gets weight of 100."""
        # Create a value with revision
        value = Value(user_id=test_user.id)
        db_session.add(value)
        await db_session.flush()
        
        revision = ValueRevision(
            value_id=value.id,
            statement="Test",
            weight_raw=50,
            is_active=True,
            origin="user",
        )
        db_session.add(revision)
        await db_session.flush()
        
        value.active_revision_id = revision.id
        await db_session.commit()
        
        await normalize_value_weights(db_session, test_user.id)
        await db_session.commit()
        
        await db_session.refresh(revision)
        assert revision.weight_normalized == Decimal("100")
    
    @pytest.mark.asyncio
    async def test_normalize_multiple_values(self, db_session, test_user):
        """Multiple values distribute weights proportionally."""
        # Create two values
        value1 = Value(user_id=test_user.id)
        value2 = Value(user_id=test_user.id)
        db_session.add(value1)
        db_session.add(value2)
        await db_session.flush()
        
        rev1 = ValueRevision(
            value_id=value1.id,
            statement="Test 1",
            weight_raw=30,
            is_active=True,
            origin="user",
        )
        rev2 = ValueRevision(
            value_id=value2.id,
            statement="Test 2",
            weight_raw=70,
            is_active=True,
            origin="user",
        )
        db_session.add(rev1)
        db_session.add(rev2)
        await db_session.flush()
        
        value1.active_revision_id = rev1.id
        value2.active_revision_id = rev2.id
        await db_session.commit()
        
        await normalize_value_weights(db_session, test_user.id)
        await db_session.commit()
        
        await db_session.refresh(rev1)
        await db_session.refresh(rev2)
        
        # 30/100 = 30%, 70/100 = 70%
        assert rev1.weight_normalized == Decimal("30")
        assert rev2.weight_normalized == Decimal("70")
    
    @pytest.mark.asyncio
    async def test_normalize_all_zero_weights(self, db_session, test_user):
        """Zero weights distribute equally."""
        value1 = Value(user_id=test_user.id)
        value2 = Value(user_id=test_user.id)
        db_session.add(value1)
        db_session.add(value2)
        await db_session.flush()
        
        rev1 = ValueRevision(
            value_id=value1.id,
            statement="Test 1",
            weight_raw=0,
            is_active=True,
            origin="user",
        )
        rev2 = ValueRevision(
            value_id=value2.id,
            statement="Test 2",
            weight_raw=0,
            is_active=True,
            origin="user",
        )
        db_session.add(rev1)
        db_session.add(rev2)
        await db_session.flush()
        
        value1.active_revision_id = rev1.id
        value2.active_revision_id = rev2.id
        await db_session.commit()
        
        await normalize_value_weights(db_session, test_user.id)
        await db_session.commit()
        
        await db_session.refresh(rev1)
        await db_session.refresh(rev2)
        
        # Equal distribution
        assert rev1.weight_normalized == Decimal("50")
        assert rev2.weight_normalized == Decimal("50")


class TestCalculateNormalizedWeights:
    """Tests for the calculate_normalized_weights function."""
    
    def test_empty_list(self):
        """Empty list returns empty list."""
        assert calculate_normalized_weights([]) == []
    
    def test_single_weight(self):
        """Single weight becomes 100."""
        result = calculate_normalized_weights([Decimal("50")])
        assert result == [Decimal("100")]
    
    def test_equal_weights(self):
        """Equal weights distribute evenly."""
        result = calculate_normalized_weights([
            Decimal("25"), Decimal("25"), Decimal("25"), Decimal("25")
        ])
        for w in result:
            assert w == Decimal("25")
    
    def test_unequal_weights(self):
        """Unequal weights normalize proportionally."""
        result = calculate_normalized_weights([
            Decimal("30"), Decimal("70")
        ])
        assert result[0] == Decimal("30")
        assert result[1] == Decimal("70")
    
    def test_different_raw_weights(self):
        """Different raw weights normalize correctly."""
        result = calculate_normalized_weights([
            Decimal("10"), Decimal("20"), Decimal("30")
        ])
        total = sum(result)
        assert abs(total - Decimal("100")) < Decimal("0.0001")
        # 10/60 = 16.67%, 20/60 = 33.33%, 30/60 = 50%
        assert abs(result[0] - Decimal("16.666666666666666666666666666666")) < Decimal("0.01")
        assert abs(result[1] - Decimal("33.333333333333333333333333333333")) < Decimal("0.01")
        assert result[2] == Decimal("50")
    
    def test_all_zero_weights(self):
        """All zero weights distribute equally."""
        result = calculate_normalized_weights([
            Decimal("0"), Decimal("0"), Decimal("0")
        ])
        for w in result:
            assert abs(w - Decimal("33.333333333333333333333333333333")) < Decimal("0.01")


class TestRedistributeWeight:
    """Tests for the redistribute_weight function."""
    
    def test_empty_list(self):
        """Empty list returns empty list."""
        assert redistribute_weight([], 0, Decimal("50")) == []
    
    def test_invalid_index(self):
        """Invalid index returns original list."""
        weights = [Decimal("50"), Decimal("50")]
        result = redistribute_weight(weights, 5, Decimal("30"))
        assert result == weights
    
    def test_single_weight(self):
        """Single weight becomes 100 regardless of input."""
        result = redistribute_weight([Decimal("100")], 0, Decimal("50"))
        assert result == [Decimal("50")]
    
    def test_increase_one_weight(self):
        """Increasing one weight decreases others proportionally."""
        weights = [Decimal("50"), Decimal("50")]
        result = redistribute_weight(weights, 0, Decimal("80"))
        
        assert result[0] == Decimal("80")
        assert result[1] == Decimal("20")
    
    def test_decrease_one_weight(self):
        """Decreasing one weight increases others proportionally."""
        weights = [Decimal("50"), Decimal("50")]
        result = redistribute_weight(weights, 0, Decimal("20"))
        
        assert result[0] == Decimal("20")
        assert result[1] == Decimal("80")
    
    def test_set_to_100(self):
        """Setting one to 100 sets others to 0."""
        weights = [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
        result = redistribute_weight(weights, 0, Decimal("100"))
        
        assert result[0] == Decimal("100")
        assert result[1] == Decimal("0")
        assert result[2] == Decimal("0")
    
    def test_set_to_0(self):
        """Setting one to 0 redistributes to others."""
        weights = [Decimal("50"), Decimal("25"), Decimal("25")]
        result = redistribute_weight(weights, 0, Decimal("0"))
        
        assert result[0] == Decimal("0")
        # Remaining 100 distributed proportionally (50/50)
        assert result[1] == Decimal("50")
        assert result[2] == Decimal("50")
    
    def test_proportional_distribution(self):
        """Others are adjusted proportionally."""
        weights = [Decimal("60"), Decimal("30"), Decimal("10")]
        result = redistribute_weight(weights, 0, Decimal("40"))
        
        assert result[0] == Decimal("40")
        # Remaining 60 distributed proportionally (30/40 = 75%, 10/40 = 25%)
        assert result[1] == Decimal("45")
        assert result[2] == Decimal("15")
    
    def test_handles_all_others_zero(self):
        """Handles case where all other weights are zero."""
        weights = [Decimal("100"), Decimal("0"), Decimal("0")]
        result = redistribute_weight(weights, 0, Decimal("50"))
        
        assert result[0] == Decimal("50")
        # Remaining 50 distributed equally among others
        assert result[1] == Decimal("25")
        assert result[2] == Decimal("25")
    
    def test_weight_over_100_clamped(self):
        """Weight over 100 is clamped."""
        weights = [Decimal("50"), Decimal("50")]
        result = redistribute_weight(weights, 0, Decimal("150"))
        
        assert result[0] == Decimal("100")
        assert result[1] == Decimal("0")
