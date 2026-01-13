"""
Episode Title Utilities
Normalizes episode titles to consistent formats for different target languages.
"""

import re
from typing import Optional


# Korean number mappings
KOREAN_NUMS = {'일': 1, '이': 2, '삼': 3, '사': 4, '오': 5, '육': 6, '칠': 7, '팔': 8, '구': 9}
KOREAN_UNITS = {'십': 10, '백': 100}

# Chinese number mappings
CHINESE_NUMS = {
    1: '一', 2: '二', 3: '三', 4: '四', 5: '五',
    6: '六', 7: '七', 8: '八', 9: '九', 10: '十'
}


def korean_num_to_arabic(korean_str: str) -> Optional[int]:
    """
    Convert Korean number string to Arabic number.

    Examples:
        일 → 1
        십 → 10
        이십일 → 21
        백오 → 105
        오십 → 50
    """
    if not korean_str:
        return None

    korean_str = korean_str.strip()

    # Handle simple single character numbers
    if korean_str in KOREAN_NUMS:
        return KOREAN_NUMS[korean_str]

    # Handle '십' alone (means 10)
    if korean_str == '십':
        return 10

    # Handle '백' alone (means 100)
    if korean_str == '백':
        return 100

    result = 0
    current = 0

    for char in korean_str:
        if char in KOREAN_NUMS:
            current = KOREAN_NUMS[char]
        elif char in KOREAN_UNITS:
            unit = KOREAN_UNITS[char]
            if current == 0:
                current = 1  # 십 = 10, 백 = 100 (implied 1)
            result += current * unit
            current = 0

    # Add any remaining current value
    result += current

    return result if result > 0 else None


def arabic_to_chinese(num: int) -> str:
    """
    Convert Arabic number to Chinese number string.

    Examples:
        1 → 一
        10 → 十
        21 → 二十一
        50 → 五十
        105 → 一百零五
    """
    if num <= 0:
        return str(num)

    if num <= 10:
        return CHINESE_NUMS[num]

    if num < 20:
        # 11-19: 十一, 十二, ...
        ones = num % 10
        return f"十{CHINESE_NUMS[ones]}" if ones > 0 else "十"

    if num < 100:
        # 20-99
        tens = num // 10
        ones = num % 10
        result = f"{CHINESE_NUMS[tens]}十"
        if ones > 0:
            result += CHINESE_NUMS[ones]
        return result

    if num < 1000:
        # 100-999
        hundreds = num // 100
        remainder = num % 100
        result = f"{CHINESE_NUMS[hundreds]}百"
        if remainder > 0:
            if remainder < 10:
                result += f"零{CHINESE_NUMS[remainder]}"
            else:
                result += arabic_to_chinese(remainder)
        return result

    # For numbers >= 1000, just return Arabic
    return str(num)


def format_episode_title(episode_num: int, target_lang: str) -> str:
    """
    Format episode title for target language.

    Args:
        episode_num: Episode number (1, 2, 3, ...)
        target_lang: Target language code

    Returns:
        Formatted episode title

    Examples:
        format_episode_title(50, 'traditional_chinese') → '第五十集'
        format_episode_title(50, 'japanese') → '第50話'
        format_episode_title(50, 'english') → 'Episode 50'
    """
    if target_lang in ('traditional_chinese', 'simplified_chinese'):
        chinese_num = arabic_to_chinese(episode_num)
        return f"第{chinese_num}集"

    elif target_lang == 'japanese':
        return f"第{episode_num}話"

    elif target_lang == 'english':
        return f"Episode {episode_num}"

    elif target_lang == 'korean':
        return f"에피소드 {episode_num}"

    else:
        # Default to simple format
        return f"Episode {episode_num}"


def normalize_episode_title_in_content(
    content: str,
    episode_num: int,
    target_lang: str
) -> str:
    """
    Normalize episode title at the beginning of translated content.

    Handles various input formats:
    - Episode 일. / Episode 십. / Episode 오십.
    - Episode 十. / Episode 五十.
    - 第一集 / 第十集
    - 에피소드 1 / 제1화

    Args:
        content: Translated content with potentially malformed episode title
        episode_num: Known episode number
        target_lang: Target language code

    Returns:
        Content with normalized episode title
    """
    if not content:
        return content

    # Get the correct formatted title
    correct_title = format_episode_title(episode_num, target_lang)

    # Split content into lines
    lines = content.split('\n')

    if not lines:
        return content

    first_line = lines[0].strip()

    # Patterns to match various malformed episode titles
    patterns = [
        # Episode + Korean number (e.g., "Episode 일.", "Episode 오십.")
        r'^Episode\s+[일이삼사오육칠팔구십백천]+\.?$',
        # Episode + Chinese number (e.g., "Episode 十.", "Episode 五十.")
        r'^Episode\s+[一二三四五六七八九十百千零]+\.?$',
        # Episode + Arabic number
        r'^Episode\s+\d+\.?$',
        # 第X集 format (Chinese)
        r'^第[一二三四五六七八九十百千零\d]+集\.?$',
        # 第X話 format (Japanese)
        r'^第\d+話\.?$',
        # 에피소드 format (Korean)
        r'^에피소드\s+\d+\.?$',
        # 제X화 format (Korean)
        r'^제\d+화\.?$',
    ]

    # Check if first line matches any pattern
    for pattern in patterns:
        if re.match(pattern, first_line, re.IGNORECASE):
            # Replace first line with correct title
            lines[0] = correct_title
            return '\n'.join(lines)

    # If no pattern matched but first line looks like a title (short, no emotion tags)
    if len(first_line) < 30 and not first_line.startswith('['):
        # Check if it contains episode-related keywords
        episode_keywords = ['episode', 'Episode', '第', '집', '話', '화', '에피소드']
        if any(kw in first_line for kw in episode_keywords):
            lines[0] = correct_title
            return '\n'.join(lines)

    return content


# Tests
if __name__ == '__main__':
    # Test Korean to Arabic conversion
    test_cases = [
        ('일', 1),
        ('이', 2),
        ('십', 10),
        ('이십', 20),
        ('이십일', 21),
        ('오십', 50),
        ('백', 100),
        ('백오', 105),
    ]

    print("Testing korean_num_to_arabic:")
    for korean, expected in test_cases:
        result = korean_num_to_arabic(korean)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{korean}' → {result} (expected {expected})")

    # Test Arabic to Chinese conversion
    print("\nTesting arabic_to_chinese:")
    cn_test_cases = [
        (1, '一'),
        (10, '十'),
        (11, '十一'),
        (21, '二十一'),
        (50, '五十'),
        (100, '一百'),
        (105, '一百零五'),
    ]

    for arabic, expected in cn_test_cases:
        result = arabic_to_chinese(arabic)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {arabic} → '{result}' (expected '{expected}')")

    # Test format_episode_title
    print("\nTesting format_episode_title:")
    print(f"  50, traditional_chinese → '{format_episode_title(50, 'traditional_chinese')}'")
    print(f"  50, japanese → '{format_episode_title(50, 'japanese')}'")
    print(f"  50, english → '{format_episode_title(50, 'english')}'")

    # Test normalize_episode_title_in_content
    print("\nTesting normalize_episode_title_in_content:")
    test_content = "Episode 十.\n\n[Neutral] Some content here."
    normalized = normalize_episode_title_in_content(test_content, 10, 'traditional_chinese')
    print(f"  Input: 'Episode 十.'")
    print(f"  Output: '{normalized.split(chr(10))[0]}'")
