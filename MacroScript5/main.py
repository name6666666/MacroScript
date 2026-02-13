import re
import subprocess
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')



class _Percent:
    def __init__(self, value):
        self.value:str = value
    def __add__(self, other):
        return self.value + other.value
    def __str__(self):
        return f'P({self.value})'
    def __repr__(self):
        return self.__str__()
class _Common:
    def __init__(self, value):
        self.value:str = value
    def __add__(self, other):
        return self.value + other.value
    def __str__(self):
        return f'C({self.value})'
    def __repr__(self):
        return self.__str__()

class MacroScriptError(Exception):
    pass

class MacroScript:
    def __init__(self, text:str, node_path:str, *, timeout=10):
        self._text = text
        self.node_path = node_path
        self.timeout = timeout
    
    def compile_js(self):
        code = 'var __code__ = "";\nfunction __final__(){;}\n'
        code += 'var __out__ = console.log;\nconsole.log = undefined;\n'
        code += self._turn_js()
        code += '__final__();\n'
        code += '__out__(__code__);'
        return code
    
    def execute(self):
        code = self.compile_js()
        try:
            result = subprocess.run(
                [self.node_path, '-e', code],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=self.timeout
            )
            if result.returncode == 0:
                return result.stdout
            else:
                raise RuntimeError(f"JavaScript execution error: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError(f"Node.js not found at {self.node_path}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("JavaScript execution timeout")

    def _separate(self) -> list[_Percent | _Common]:
        result = []
        lines = self._text.splitlines(keepends=True)
        for line in lines:
            if line and line[0] == '%':
                result.append(_Percent(line[1:]))
            else:
                result.append(_Common(line))
        if not result:
            return []
        new_result = [result[0]]
        for i in result[1:]:
            if (t:=type(i)) == type(new_result[-1]):
                new_result[-1] = t(new_result[-1] + i)
            else:
                new_result.append(i)
        return new_result

    @staticmethod
    def _get_macro_func(code:str) -> list[str]:
        pattern = re.compile(r'function\s+\$(\w+)')
        return pattern.findall(code)

    def _turn_js(self):
        code = ''
        sep_result = self._separate()
        macro_funcs = []
        for i in sep_result:
            if type(i) == _Percent:
                macro_funcs += self._get_macro_func(i.value)
                code += i.value
            else:
                if not macro_funcs:
                    code += f'__code__ += `{i.value.rstrip()}`;\n'
                else:
                    pattern = re.compile(r'\b(' + '|'.join(map(re.escape, macro_funcs)) + r')(?:\s*\([^)]*\))?')
                    parts = []
                    last = 0
                    for match in pattern.finditer(i.value):
                        start, end = match.span()
                        if start > last:
                            parts.append(i.value[last:start])
                        matched = match.group(0)
                        if '(' in matched:
                            parts.append((matched,))
                        else:
                            parts.append([matched])
                        last = end
                    if last < len(i.value):
                        parts.append(i.value[last:])

                    for i in range(len(parts)):
                        part = parts[i]
                        if isinstance(part, str):
                            parts[i] = f'__code__ += `{part.rstrip()}`;\n'
                        elif isinstance(part, tuple):
                            parts[i] = f'${part[0]};\n'
                        elif isinstance(part, list):
                            parts[i] = f'${part[0]}();\n'
                        else:
                            raise TypeError(f'Invalid type {type(part)}.')
                    code += ''.join(parts)
        return code

