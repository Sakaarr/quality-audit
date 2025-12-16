
from enum import Enum
from dataclasses import dataclass, field
import keyword
from typing import Any, Dict, List, Optional, Tuple, Union
from decimal import ROUND_HALF_UP, Clamped, Decimal
import operator
import re
import ast
from numpy import number
import pandas as pd

@dataclass
class CalculationResult:
    expression: str
    expected_result: Decimal
    actual_result: Decimal
    is_correct: bool
    location: str
    calculation_type: str
    tolerance: Decimal
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "expression": self.expression,
            "expected_result": float(self.expected_result),
            "actual_result": float(self.actual_result),
            "is_correct": self.is_correct,
            "location": self.location,
            "calculation_type": self.calculation_type,
            "tolerance": float(self.tolerance),
            "context": self.context
        }


class CalculationValidator:
    def __init__(self, tolerance: float = 0.01):
        self.tolerance = Decimal(str(tolerance))
        self.operators = {
            '+': operator.add,
            '-': operator.sub,
            '*': operator.mul,
            '/': operator.truediv,
            '×': operator.mul,  # Unicode multiplication
            '÷': operator.truediv,  # Unicode division
            '%': self._percentage_op,
        }
        self.patterns = self._initialize_patterns()

    def _initialize_patterns(self) -> Dict[str, re.Pattern]:
        return {
            # Matches: 25 + 17 = 42, 144 ÷ 12 = 12, 12 × 8 = 96
            "basic_arithmetic": re.compile(
                r'(\d+(?:\.\d+)?)\s*([+\-*/×÷])\s*(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            # Matches: 0.20 × 250 = 50
            "decimal_multiplication": re.compile(
                r'(\d+(?:\.\d+)?)\s*[×*]\s*(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            # Matches: 20% of 250 = 50 (capturing the result after =)
            "percentage_of": re.compile(
                r'(\d+(?:\.\d+)?)%\s+of\s+(\d+(?:\.\d+)?)\s*=.*?=\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            # Matches: 300 × 1.15 = 345
            "percentage_increase": re.compile(
                r'(\d+(?:\.\d+)?)\s*[×*]\s*(1\.\d+)\s*=\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            # Matches: 500 × 0.90 = 450
            "percentage_decrease": re.compile(
                r'(\d+(?:\.\d+)?)\s*[×*]\s*(0\.\d+)\s*=\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            # Matches: (5000 × 8 × 2) / 100 = 800
            "complex_formula": re.compile(
                r'\((\d+(?:\.\d+)?)\s*[×*]\s*(\d+(?:\.\d+)?)\s*[×*]\s*(\d+(?:\.\d+)?)\)\s*/\s*(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
        }
    
    def _percentage_op(self, a: Decimal, b: Decimal) -> Decimal:
        return a * (b / Decimal("100"))

    def _safe_eval(self, expression: str) -> Decimal:
        try:
            node = ast.parse(expression, mode="eval")
            if not self._is_safe_ast(node):
                raise ValueError("Unsafe expression")
            return self._eval_node(node.body)
        except Exception:
            raise ValueError(f"Cannot evaluate expression: {expression}")

    def _is_safe_ast(self, node: ast.AST) -> bool:
        safe_node_types = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
        )
        for child in ast.walk(node):
            if not isinstance(child, safe_node_types):
                return False
        return True

    def _eval_node(self, node: ast.AST) -> Decimal:
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        elif isinstance(node, ast.Num):
            return Decimal(str(node.n))
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            
            # Map AST operator types to our operator functions
            op_map = {
                ast.Add: '+',
                ast.Sub: '-',
                ast.Mult: '*',
                ast.Div: '/',
                ast.Mod: '%'
            }
            op_symbol = op_map.get(type(node.op))
            if op_symbol and op_symbol in self.operators:
                return self.operators[op_symbol](left, right)
            raise ValueError(f"Unsupported operator: {type(node.op)}")
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.UAdd):
                return operand
            raise ValueError(f"Unsupported unary operator: {type(node.op)}")
        else:
            raise ValueError(f"Unsupported node type: {type(node)}")

    def extract_calculations_from_text(
        self, 
        text: str, 
        location: str = "unknown"
    ) -> List[CalculationResult]:
        """Extract and validate calculations from plain text."""
        results: List[CalculationResult] = []
        
        # Check for complex formulas first (e.g., (5000 × 8 × 2) / 100 = 800)
        matches = self.patterns['complex_formula'].finditer(text)
        for match in matches:
            val1, val2, val3, divisor, actual = match.groups()
            try:
                expected = self._safe_eval(f"({val1} * {val2} * {val3}) / {divisor}")
                result = self._create_calculation_result(
                    match.group(0),
                    expected,
                    Decimal(actual),
                    location,
                    "complex_formula"
                )
                results.append(result)
            except Exception:
                continue
        
        # Check for basic arithmetic (including × and ÷)
        matches = self.patterns['basic_arithmetic'].finditer(text)
        for match in matches:
            left, op, right, actual = match.groups()
            try:
                # Normalize operators
                normalized_op = op
                if op == '×':
                    normalized_op = '*'
                elif op == '÷':
                    normalized_op = '/'
                    
                expected = self._safe_eval(f"{left} {normalized_op} {right}")
                result = self._create_calculation_result(
                    f"{left} {op} {right} = {actual}",
                    expected,
                    Decimal(actual),
                    location,
                    "basic_arithmetic"
                )
                results.append(result)
            except Exception:
                continue
        
        # Check for percentage of pattern (20% of 250 = 0.20 × 250 = 50)
        matches = self.patterns['percentage_of'].finditer(text)
        for match in matches:
            try:
                perc, val, actual = match.groups()
                expected = self._safe_eval(f"{val} * {perc} / 100")
                result = self._create_calculation_result(
                    f"{perc}% of {val} = {actual}",
                    expected,
                    Decimal(actual),
                    location,
                    "percentage"
                )
                results.append(result)
            except Exception:
                continue
        
        # Check for decimal multiplication (0.20 × 250 = 50)
        matches = self.patterns['decimal_multiplication'].finditer(text)
        for match in matches:
            try:
                val1, val2, actual = match.groups()
                expected = self._safe_eval(f"{val1} * {val2}")
                result = self._create_calculation_result(
                    f"{val1} × {val2} = {actual}",
                    expected,
                    Decimal(actual),
                    location,
                    "multiplication"
                )
                results.append(result)
            except Exception:
                continue
        
        return results

    def extract_calculations_from_table(
        self, 
        table_data: List[List[str]], 
        location: str = "unknown"
    ) -> List[CalculationResult]:
        """Validate calculations within table data by checking column totals."""
        results: List[CalculationResult] = []
        
        if not table_data or len(table_data) < 2:
            return results
        
        try:
            # Create DataFrame
            df = pd.DataFrame(table_data).map(lambda x: str(x) if x is not None else "")
            
            # Iterate through rows to find the "Total" row
            for row_idx in range(len(df)):
                row = df.iloc[row_idx]
                row_text = " ".join(row.astype(str)).lower()
                
                # Check if this is a Total row
                if any(keyword in row_text for keyword in ["total", "sum", "subtotal"]):
                    
                    # Iterate through the cells in this Total row to find the stated total(s)
                    for col_idx, cell_value in enumerate(row):
                        # Extract the number from the total cell
                        numbers = re.findall(r'[\d,]+\.?\d*', str(cell_value))
                        if not numbers:
                            continue
                            
                        # Clean and convert the stated total
                        try:
                            stated_total = Decimal(numbers[0].replace(',', ''))
                        except:
                            continue

                       
                        values_to_sum = []
                        
                        for prev_row_idx in range(row_idx):
                            prev_cell = df.iloc[prev_row_idx, col_idx]
                            
                            prev_nums = re.findall(r'[\d,]+\.?\d*', str(prev_cell))
                            
                            if prev_nums:
                                try:
                                    val = Decimal(prev_nums[0].replace(',', ''))
                                    values_to_sum.append(val)
                                except:
                                    continue

                        if values_to_sum:
                            calculated_total = sum(values_to_sum, Decimal("0"))
                            
                            result = self._create_calculation_result(
                                f"Column total at row {row_idx + 1}, col {col_idx + 1}",
                                calculated_total,
                                stated_total,
                                f"{location} - Row {row_idx + 1}",
                                "table_total",
                                context={
                                    "row_index": row_idx,
                                    "column_index": col_idx,
                                    "values_summed": len(values_to_sum)
                                }
                            )
                            results.append(result)

        except Exception as e:
            print(f"Error processing table: {e}")
        
        return results

    def _create_calculation_result(
        self,
        expression: str,
        expected: Decimal,
        actual: Decimal,
        location: str,
        calc_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> CalculationResult:
        rounded_expected = expected.quantize(self.tolerance, rounding=ROUND_HALF_UP)
        rounded_actual = actual.quantize(self.tolerance, rounding=ROUND_HALF_UP)
        is_correct = abs(rounded_expected - rounded_actual) <= self.tolerance
        
        return CalculationResult(
            expression=expression,
            expected_result=rounded_expected,
            actual_result=rounded_actual,
            is_correct=is_correct,
            location=location,
            calculation_type=calc_type,
            tolerance=self.tolerance,
            context=context or {}
        )