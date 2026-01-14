import re
MACHINEID_PATTERN = r"^[MF][A-D][1-8]$"

def ISVALIDMACHINEID(MACHINEID: str) -> bool:
    if MACHINEID is None:
        return False
    return re.fullmatch(MACHINEID_PATTERN, str(MACHINEID)) is not None

def KEEPDIGITSONLY(TEXT: str) -> str:
    """
    Returns a string containing only the digit characters from TEXT.
    """
    if TEXT is None:
        return ""

    DIGITS = ""
    for CH in str(TEXT):
        if CH.isdigit():
            DIGITS = DIGITS + CH

    return DIGITS
