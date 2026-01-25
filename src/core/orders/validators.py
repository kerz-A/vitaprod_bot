"""
Validators for order data.
"""

import re
from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple


class PhoneValidator:
    """Validate and normalize phone numbers."""
    
    # Pattern for Russian phone numbers
    PHONE_PATTERN = re.compile(
        r'^(?:\+7|8|7)?[\s\-]?\(?(\d{3})\)?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})$'
    )
    
    @classmethod
    def validate(cls, phone: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate and normalize phone number.
        
        Returns:
            Tuple of (is_valid, normalized_phone, error_message)
        """
        # Remove extra spaces
        phone = phone.strip()
        
        if not phone:
            return False, None, "Номер телефона не может быть пустым"
        
        # Try to match pattern
        match = cls.PHONE_PATTERN.match(phone)
        
        if not match:
            return False, None, (
                "Неверный формат номера. Пожалуйста, введите номер в формате:\n"
                "+7 912 345-67-89 или 89123456789"
            )
        
        # Normalize to +7 XXX XXX-XX-XX format
        groups = match.groups()
        normalized = f"+7 {groups[0]} {groups[1]}-{groups[2]}-{groups[3]}"
        
        return True, normalized, None


class DateValidator:
    """Validate delivery dates."""
    
    # Minimum days for delivery (next day)
    MIN_DAYS_AHEAD = 1
    
    # Maximum days ahead for scheduling
    MAX_DAYS_AHEAD = 30
    
    # Weekend days (Saturday=5, Sunday=6)
    WEEKEND_DAYS = {5, 6}
    
    @classmethod
    def validate(cls, date_str: str) -> Tuple[bool, Optional[date], Optional[str], bool]:
        """
        Validate delivery date.
        
        Returns:
            Tuple of (is_valid, parsed_date, error_message, is_weekend)
        """
        date_str = date_str.strip()
        
        if not date_str:
            return False, None, "Дата не может быть пустой", False
        
        # Try different date formats
        formats = [
            "%d.%m.%Y",     # 28.01.2026
            "%d.%m.%y",     # 28.01.26
            "%d.%m",        # 28.01 (current year)
            "%d/%m/%Y",     # 28/01/2026
            "%d/%m",        # 28/01
        ]
        
        parsed_date = None
        today = date.today()
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt).date()
                
                # If year not in format, use current year
                if "%Y" not in fmt and "%y" not in fmt:
                    parsed = parsed.replace(year=today.year)
                    # If date is in past, assume next year
                    if parsed < today:
                        parsed = parsed.replace(year=today.year + 1)
                
                parsed_date = parsed
                break
            except ValueError:
                continue
        
        # Handle relative dates
        if parsed_date is None:
            lower = date_str.lower()
            if lower in ["завтра", "tomorrow"]:
                parsed_date = today + timedelta(days=1)
            elif lower in ["послезавтра"]:
                parsed_date = today + timedelta(days=2)
            elif lower in ["сегодня", "today"]:
                parsed_date = today
        
        if parsed_date is None:
            return False, None, (
                "Не удалось распознать дату. Пожалуйста, введите в формате:\n"
                "ДД.ММ.ГГГГ (например, 28.01.2026) или 'завтра'"
            ), False
        
        # Check if date is not in the past
        if parsed_date < today:
            return False, None, "Дата не может быть в прошлом", False
        
        # Check minimum days ahead
        min_date = today + timedelta(days=cls.MIN_DAYS_AHEAD)
        if parsed_date < min_date:
            return False, None, (
                f"Минимальный срок — {cls.MIN_DAYS_AHEAD} день. "
                f"Ближайшая доступная дата: {min_date.strftime('%d.%m.%Y')}"
            ), False
        
        # Check maximum days ahead
        max_date = today + timedelta(days=cls.MAX_DAYS_AHEAD)
        if parsed_date > max_date:
            return False, None, (
                f"Максимальный срок планирования — {cls.MAX_DAYS_AHEAD} дней. "
                f"Пожалуйста, выберите дату до {max_date.strftime('%d.%m.%Y')}"
            ), False
        
        # Check if weekend
        is_weekend = parsed_date.weekday() in cls.WEEKEND_DAYS
        
        return True, parsed_date, None, is_weekend


class TimeValidator:
    """Validate delivery time."""
    
    # Working hours
    WORK_START = time(8, 0)
    WORK_END = time(18, 0)
    
    @classmethod
    def validate(cls, time_str: str) -> Tuple[bool, Optional[Tuple[time, time]], Optional[str]]:
        """
        Validate delivery time slot.
        
        Returns:
            Tuple of (is_valid, (time_from, time_to), error_message)
        """
        time_str = time_str.strip().lower()
        
        if not time_str:
            return False, None, "Время не может быть пустым"
        
        # Handle predefined slots
        predefined_slots = {
            "утро": (time(8, 0), time(12, 0)),
            "утром": (time(8, 0), time(12, 0)),
            "день": (time(12, 0), time(16, 0)),
            "днём": (time(12, 0), time(16, 0)),
            "днем": (time(12, 0), time(16, 0)),
            "вечер": (time(16, 0), time(18, 0)),
            "вечером": (time(16, 0), time(18, 0)),
            "любое": (time(8, 0), time(18, 0)),
            "любое время": (time(8, 0), time(18, 0)),
            "в течение дня": (time(8, 0), time(18, 0)),
        }
        
        if time_str in predefined_slots:
            return True, predefined_slots[time_str], None
        
        # Try to parse time range (e.g., "10:00-14:00" or "с 10 до 14")
        range_patterns = [
            r'(\d{1,2})[:\.]?(\d{2})?\s*[-–до]\s*(\d{1,2})[:\.]?(\d{2})?',  # 10:00-14:00
            r'с\s*(\d{1,2})[:\.]?(\d{2})?\s*до\s*(\d{1,2})[:\.]?(\d{2})?',  # с 10 до 14
        ]
        
        for pattern in range_patterns:
            match = re.match(pattern, time_str)
            if match:
                groups = match.groups()
                hour_from = int(groups[0])
                min_from = int(groups[1]) if groups[1] else 0
                hour_to = int(groups[2])
                min_to = int(groups[3]) if groups[3] else 0
                
                try:
                    time_from = time(hour_from, min_from)
                    time_to = time(hour_to, min_to)
                    
                    # Validate working hours
                    if time_from < cls.WORK_START:
                        return False, None, f"Мы работаем с {cls.WORK_START.strftime('%H:%M')}"
                    if time_to > cls.WORK_END:
                        return False, None, f"Мы работаем до {cls.WORK_END.strftime('%H:%M')}"
                    if time_from >= time_to:
                        return False, None, "Время начала должно быть меньше времени окончания"
                    
                    return True, (time_from, time_to), None
                except ValueError:
                    pass
        
        # Try to parse single time (e.g., "в 10:00" or "после 14")
        single_patterns = [
            r'в?\s*(\d{1,2})[:\.]?(\d{2})?',  # в 10:00 or 10
            r'после\s*(\d{1,2})[:\.]?(\d{2})?',  # после 14
        ]
        
        for pattern in single_patterns:
            match = re.match(pattern, time_str)
            if match:
                groups = match.groups()
                hour = int(groups[0])
                minutes = int(groups[1]) if groups[1] else 0
                
                try:
                    parsed_time = time(hour, minutes)
                    
                    if parsed_time < cls.WORK_START:
                        return False, None, f"Мы работаем с {cls.WORK_START.strftime('%H:%M')}"
                    if parsed_time > cls.WORK_END:
                        return False, None, f"Мы работаем до {cls.WORK_END.strftime('%H:%M')}"
                    
                    # Create 2-hour window
                    end_hour = min(hour + 2, cls.WORK_END.hour)
                    time_to = time(end_hour, minutes)
                    
                    return True, (parsed_time, time_to), None
                except ValueError:
                    pass
        
        return False, None, (
            "Не удалось распознать время. Пожалуйста, введите:\n"
            "• Интервал: 10:00-14:00 или 'с 10 до 14'\n"
            "• Или: 'утро', 'день', 'вечер', 'любое время'"
        )


class AddressValidator:
    """Validate delivery address."""
    
    MIN_LENGTH = 10
    
    @classmethod
    def validate(cls, address: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate delivery address.
        
        Returns:
            Tuple of (is_valid, normalized_address, error_message)
        """
        address = address.strip()
        
        if not address:
            return False, None, "Адрес не может быть пустым"
        
        if len(address) < cls.MIN_LENGTH:
            return False, None, (
                "Адрес слишком короткий. Пожалуйста, укажите полный адрес:\n"
                "город, улица, дом, офис/квартира"
            )
        
        return True, address, None


class QuantityValidator:
    """Validate product quantity."""
    
    MIN_QUANTITY = 0.5  # Minimum 500g
    MAX_QUANTITY = 1000  # Maximum 1 ton per item
    
    @classmethod
    def validate(cls, quantity_str: str) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Validate quantity.
        
        Returns:
            Tuple of (is_valid, quantity_kg, error_message)
        """
        quantity_str = quantity_str.strip().lower()
        
        if not quantity_str:
            return False, None, "Количество не может быть пустым"
        
        # Remove units and extra text
        quantity_str = re.sub(r'\s*(кг|kg|килограмм|килограммов)\.?\s*', '', quantity_str)
        quantity_str = quantity_str.replace(',', '.')
        
        try:
            quantity = float(quantity_str)
        except ValueError:
            return False, None, "Не удалось распознать количество. Введите число, например: 10"
        
        if quantity < cls.MIN_QUANTITY:
            return False, None, f"Минимальное количество: {cls.MIN_QUANTITY} кг"
        
        if quantity > cls.MAX_QUANTITY:
            return False, None, f"Максимальное количество: {cls.MAX_QUANTITY} кг"
        
        return True, quantity, None
