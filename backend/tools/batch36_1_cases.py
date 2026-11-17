"""36-1: 50 deterministic, realistic Python scenarios for offline style evaluation.

Every sample is authored for this audit, not collected from external projects.
All code is intended to be executable without network, file writes, or packages
outside the Python standard library. Cases exercise style preferences, safe
closed transforms, disagreement, ordinary application code, and no-op paths.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    case_id: str
    group: str
    name: str
    style_code: str
    target_code: str
    version: str = "v1"
    stdin: str | None = None
    purpose: str = "exploratory"


CASES: list[Case] = []


def add(group: str, name: str, style: str, target: str, *,
        version: str = "v1", stdin: str | None = None,
        purpose: str = "exploratory") -> None:
    CASES.append(Case(f"R{len(CASES) + 1:02d}", group, name,
                      style, target, version, stdin, purpose))


# 1. Signature / async: the constrained patterns introduced in Batch31.
add("signature", "기본 인자 선호", "def _price(x=3):\n    return x\nprint(_price())\n",
    "def _price(x):\n    return x\nprint(_price(3))\n", purpose="expected_candidate")
add("signature", "가변 위치 인자 선호", "def _sum(*args):\n    x, y = args\n    return x + y\nprint(_sum(2, 4))\n",
    "def _sum(x, y):\n    return x + y\nprint(_sum(2, 4))\n", purpose="expected_candidate")
add("signature", "가변 키워드 인자 선호", "def _sum(**kwargs):\n    x = kwargs['x']\n    y = kwargs['y']\n    return x + y\nprint(_sum(x=2, y=4))\n",
    "def _sum(x, y):\n    return x + y\nprint(_sum(x=2, y=4))\n", purpose="expected_candidate")
add("signature", "비동기 함수 정의 선호", "import asyncio\nasync def _job():\n    return 5\nprint(asyncio.run(_job()))\n",
    "import asyncio\ndef _job():\n    return 5\nprint(_job())\n", purpose="expected_candidate")
add("signature", "await 표현 선호", "import asyncio\nasync def _job():\n    return await asyncio.sleep(0, result=5)\nprint(asyncio.run(_job()))\n",
    "import asyncio\nasync def _job():\n    return 5\nprint(asyncio.run(_job()))\n", purpose="expected_candidate")

# 2. Closed transformer + intentionally non-matching shapes.
add("closed", "비동기 구조 추출", "import asyncio\nasync def _job():\n    return 5\nasync def _runner():\n    return await _job()\nprint(asyncio.run(_runner()))\n",
    "import asyncio\nasync def _job():\n    return 5\nprint(asyncio.run(_job()))\n", purpose="expected_candidate")
add("closed", "긴 함수 본문 선호", "def _show():\n" + "".join(f"    print({i})\n" for i in range(12)) + "_show()\n",
    "def _show():\n    for item in [" + ", ".join(str(i) for i in range(12)) + "]:\n        print(item)\n_show()\n", purpose="expected_candidate")
add("closed", "미사용 인자: 안전하게 보류", "def _f(x=3):\n    return x\nprint(_f())\n",
    "def _f(x):\n    return 3\nprint(_f(3))\n", purpose="negative_shape")
add("closed", "인자 1개: varargs 보류", "def _f(*args):\n    x, y = args\n    return x + y\nprint(_f(2, 4))\n",
    "def _f(x):\n    return x\nprint(_f(2))\n", purpose="negative_shape")
add("closed", "반복 없는 함수: 긴 함수 보류", "def _f():\n" + "".join(f"    print({i})\n" for i in range(11)) + "_f()\n",
    "def _f():\n    print('hi')\n_f()\n", purpose="negative_shape")

# 3. Explicit/implicit defaults with a clearly one-sided preference.
add("defaults", "sorted 명시적 기본 인자", "out = sorted([4, 1, 3], reverse=False)\nprint(out)\n",
    "out = sorted([4, 1, 3])\nprint(out)\n", purpose="expected_candidate")
add("defaults", "sorted 암묵적 기본 인자", "out = sorted([4, 1, 3])\nprint(out)\n",
    "out = sorted([4, 1, 3], reverse=False)\nprint(out)\n", purpose="expected_candidate")
add("defaults", "strip(None) 명시", "s = '  demo  '\nout = s.strip(None)\nprint(out)\n",
    "s = '  demo  '\nout = s.strip()\nprint(out)\n", purpose="expected_candidate")
add("defaults", "strip() 암묵", "s = '  demo  '\nout = s.strip()\nprint(out)\n",
    "s = '  demo  '\nout = s.strip(None)\nprint(out)\n", purpose="expected_candidate")
add("defaults", "sorted가 이미 선호 스타일", "out = sorted([2, 1], reverse=False)\nprint(out)\n",
    "out = sorted([9, 1], reverse=False)\nprint(out)\n", purpose="no_preference_gap")


def sorted_examples(explicit: int, implicit: int) -> str:
    lines = [f"values_{i} = sorted([{i+3}, {i}], reverse=False)" for i in range(explicit)]
    lines += [f"simple_{i} = sorted([{i+7}, {i}])" for i in range(implicit)]
    return "\n".join(lines + ["print(values_0)"]) + "\n"


def strip_examples(explicit: int, implicit: int) -> str:
    lines = ["word = ' a b '"]
    lines += [f"e_{i} = word.strip(None)" for i in range(explicit)]
    lines += [f"i_{i} = word.strip()" for i in range(implicit)]
    return "\n".join(lines + ["print(e_0)"]) + "\n"


# 4. Mixed preferences from Batch35-5, ambiguous, and legacy compatibility.
add("dominance", "sorted 3:1 명시 우세", sorted_examples(3, 1),
    "out = sorted([8, 3])\nprint(out)\n", purpose="dominance")
add("dominance", "sorted 1:3 암묵 우세", sorted_examples(1, 3),
    "out = sorted([8, 3], reverse=False)\nprint(out)\n", purpose="dominance")
add("dominance", "strip 3:1 명시 우세", strip_examples(3, 1),
    "word = '  a  '\nout = word.strip()\nprint(out)\n", purpose="dominance")
add("dominance", "strip 1:3 암묵 우세", strip_examples(1, 3),
    "word = '  a  '\nout = word.strip(None)\nprint(out)\n", purpose="dominance")
add("dominance", "sorted 2:1 판단 보류", sorted_examples(2, 1),
    "out = sorted([8, 3])\nprint(out)\n", purpose="ambiguous")

# 5. List construction, mapping, and filtering.
add("lists", "리스트 컴프리헨션 선호", "xs = [1, 2, 3]\nout = [x * 2 for x in xs]\nprint(out)\n",
    "xs = [1, 2, 3]\nout = []\nfor x in xs:\n    out.append(x * 2)\nprint(out)\n")
add("lists", "for/append 선호", "xs = [1, 2, 3]\nout = []\nfor x in xs:\n    out.append(x + 1)\nprint(out)\n",
    "xs = [1, 2, 3]\nout = [x + 1 for x in xs]\nprint(out)\n")
add("lists", "양수 목록 필터링", "xs = [-2, 0, 5]\nout = [x for x in xs if x > 0]\nprint(out)\n",
    "xs = [-2, 0, 5]\nout = []\nfor x in xs:\n    if x > 0:\n        out.append(x)\nprint(out)\n")
add("lists", "두 리스트 연결", "a = [1, 2]\nb = [3, 4]\na.extend(b)\nprint(a)\n",
    "a = [1, 2]\nb = [3, 4]\nfor x in b:\n    a.append(x)\nprint(a)\n")
add("lists", "색인 직접 접근", "data = ['a', 'b']\nfor i in range(len(data)):\n    print(data[i])\n",
    "data = ['a', 'b']\nfor value in data:\n    print(value)\n")

# 6. Dictionaries and sets.
add("mapping", "딕셔너리 컴프리헨션", "xs = [1, 2, 3]\nd = {x: x * x for x in xs}\nprint(d)\n",
    "xs = [1, 2, 3]\nd = {}\nfor x in xs:\n    d[x] = x * x\nprint(d)\n")
add("mapping", "딕셔너리 누적 루프", "xs = [1, 2]\nd = {}\nfor x in xs:\n    d[x] = x + 2\nprint(d)\n",
    "xs = [1, 2]\nd = {x: x + 2 for x in xs}\nprint(d)\n")
add("mapping", "집합 컴프리헨션", "xs = [1, 2, 2]\ns = {x * 2 for x in xs}\nprint(sorted(s))\n",
    "xs = [1, 2, 2]\ns = set()\nfor x in xs:\n    s.add(x * 2)\nprint(sorted(s))\n")
add("mapping", "집합 추가 루프", "xs = [1, 2, 2]\ns = set()\nfor x in xs:\n    s.add(x)\nprint(sorted(s))\n",
    "xs = [1, 2, 2]\ns = {x for x in xs}\nprint(sorted(s))\n")
add("mapping", "딕셔너리 get 기본값", "d = {'a': 2}\nprint(d.get('a', 0))\n",
    "d = {'a': 2}\nprint(d['a'])\n")

# 7. Iteration choices.
add("iteration", "enumerate 인덱스와 값", "xs = ['a', 'b']\nfor i, value in enumerate(xs):\n    print(i, value)\n",
    "xs = ['a', 'b']\nfor i in range(len(xs)):\n    print(i, xs[i])\n")
add("iteration", "range 직접 순회", "xs = [2, 3]\nfor value in xs:\n    print(value)\n",
    "xs = [2, 3]\nfor i in range(len(xs)):\n    print(xs[i])\n")
add("iteration", "카운트 while과 for", "for i in range(3):\n    print(i)\n",
    "i = 0\nwhile i < 3:\n    print(i)\n    i += 1\n")
add("iteration", "반복 조건과 break", "xs = [1, 4, 8]\nfor x in xs:\n    if x > 5:\n        break\n    print(x)\n",
    "xs = [1, 4, 8]\nfor x in xs:\n    print(x)\n")
add("iteration", "2중 for와 조건문", "xs = [1, 2]\nfor x in xs:\n    for y in xs:\n        if x < y:\n            print(x, y)\n",
    "xs = [1, 2]\nfor x in xs:\n    for y in xs:\n        print(x, y)\n")

# 8. Conditions and return style.
add("conditions", "삼항 조건식", "x = 4\ny = 'big' if x >= 3 else 'small'\nprint(y)\n",
    "x = 4\nif x >= 3:\n    y = 'big'\nelse:\n    y = 'small'\nprint(y)\n")
add("conditions", "if/else 대입", "x = 4\nif x >= 3:\n    y = 'big'\nelse:\n    y = 'small'\nprint(y)\n",
    "x = 4\ny = 'big' if x >= 3 else 'small'\nprint(y)\n")
add("conditions", "불리언 직접 반환", "def is_large(n):\n    return n > 3\nprint(is_large(4))\n",
    "def is_large(n):\n    if n > 3:\n        return True\n    return False\nprint(is_large(4))\n")
add("conditions", "논리적 결합", "x = 3\nif x > 0 and x < 9:\n    print('ok')\n",
    "x = 3\nif x > 0:\n    if x < 9:\n        print('ok')\n")
add("conditions", "패턴 매칭 비교", "command = 'start'\nmatch command:\n    case 'start':\n        print('go')\n    case _:\n        print('stop')\n",
    "command = 'start'\nif command == 'start':\n    print('go')\nelse:\n    print('stop')\n")

# 9. Function style and syntax restrictions.
add("functions", "lambda와 함수 정의", "inc = lambda x: x + 1\nprint(inc(3))\n",
    "def inc(x):\n    return x + 1\nprint(inc(3))\n")
add("functions", "명시적 함수 정의", "def inc(x):\n    return x + 1\nprint(inc(3))\n",
    "inc = lambda x: x + 1\nprint(inc(3))\n")
add("functions", "키워드로 호출", "def combine(a, b):\n    return a + b\nprint(combine(a=2, b=3))\n",
    "def combine(a, b):\n    return a + b\nprint(combine(2, 3))\n")
add("functions", "타입 힌트 선호", "def total(n: int) -> int:\n    return n + 1\nprint(total(3))\n",
    "def total(n):\n    return n + 1\nprint(total(3))\n")
add("functions", "람다/컴프리헨션 복합", "nums = [1, 2, 3]\ninc = lambda x: x + 1\nprint([inc(x) for x in nums])\n",
    "nums = [1, 2, 3]\ndef inc(x):\n    return x + 1\nout = []\nfor x in nums:\n    out.append(inc(x))\nprint(out)\n")

# 10. Integration: realistic I/O, exceptions, sorting and legacy snapshots.
add("integration", "표준 입력 숫자 검증", "price = int(input())\nprint(price + 2)\n",
    "price = int(input())\nprint(price * 2)\n", stdin="5\n", purpose="same_structure_different_behavior")
add("integration", "예외 처리 경로", "try:\n    value = int('7')\nexcept ValueError:\n    value = 0\nprint(value)\n",
    "value = int('7')\nprint(value)\n")
add("integration", "데이터 정렬과 추출", "data = [9, 2, 5]\nprint(sorted(data))\n",
    "data = [9, 2, 5]\ndata.sort()\nprint(data)\n")
add("integration", "문자열 가공과 출력", "name = ' A,B '\nprint(name.strip().split(','))\n",
    "name = ' A,B '\nprint(name.replace(' ', '').split(','))\n")
add("integration", "레거시 스타일 메트릭", "xs = [1, 2, 3]\nprint([x * 2 for x in xs])\n",
    "xs = [1, 2, 3]\nout = []\nfor x in xs:\n    out.append(x * 2)\nprint(out)\n", version="legacy", purpose="legacy_compat")


assert len(CASES) == 50, f"Expected exactly 50, got {len(CASES)}"
