"""Tools package — all CrewAI BaseTool subclasses / Gói công cụ"""
from tools.mt5_tools import (
    MT5ConnectionTool,
    MT5FetchDataTool,
    MT5AccountInfoTool,
    MT5PlaceOrderTool,
    MT5GetPositionsTool,
    MT5ClosePositionTool,
)
from tools.chart_tools import GenerateCandlestickChartTool, GeneratePlotlyChartTool
from tools.pattern_tools import PatternMatchTool, SupportResistanceTool
from tools.indicator_tools import CalculateIndicatorsTool
from tools.report_tools import GenerateHTMLReportTool, GeneratePDFReportTool

__all__ = [
    "MT5ConnectionTool", "MT5FetchDataTool", "MT5AccountInfoTool",
    "MT5PlaceOrderTool", "MT5GetPositionsTool", "MT5ClosePositionTool",
    "GenerateCandlestickChartTool", "GeneratePlotlyChartTool",
    "PatternMatchTool", "SupportResistanceTool",
    "CalculateIndicatorsTool",
    "GenerateHTMLReportTool", "GeneratePDFReportTool",
]
