//+------------------------------------------------------------------+
//| FX Navigators - XAUUSD H1 Benchmark Exporter                     |
//| Copy into MQL5/Scripts, compile in MetaEditor, run on any chart. |
//+------------------------------------------------------------------+
#property copyright "FX Navigators"
#property version   "1.00"
#property script_show_inputs

input string          InpSymbol       = "XAUUSD.vx";
input ENUM_TIMEFRAMES InpTimeframe    = PERIOD_H1;
input datetime        InpStart        = D'2022.01.01 00:00:00';
input datetime        InpEnd          = D'2025.12.31 23:59:59';
input string          InpOutputFile   = "FXNavigators_XAUUSD_H1.csv";
input bool            InpCommonFolder = true;

void OnStart()
{
   if(InpEnd <= InpStart)
   {
      Print("Export failed: end time must be after start time.");
      return;
   }

   if(!SymbolSelect(InpSymbol, true))
   {
      PrintFormat("Export failed: could not select symbol %s. Error=%d", InpSymbol, GetLastError());
      return;
   }

   MqlRates rates[];
   ArraySetAsSeries(rates, false);

   int copied = -1;
   for(int attempt = 0; attempt < 20; attempt++)
   {
      ResetLastError();
      copied = CopyRates(InpSymbol, InpTimeframe, InpStart, InpEnd, rates);
      if(copied > 0)
         break;
      Sleep(500);
   }

   if(copied <= 0)
   {
      PrintFormat(
         "Export failed: CopyRates returned %d for %s. Error=%d. Open an H1 chart, scroll back, then run again.",
         copied,
         InpSymbol,
         GetLastError()
      );
      return;
   }

   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ;
   if(InpCommonFolder)
      flags |= FILE_COMMON;

   ResetLastError();
   int handle = FileOpen(InpOutputFile, flags, ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("Export failed: could not open %s. Error=%d", InpOutputFile, GetLastError());
      return;
   }

   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);

   FileWrite(
      handle,
      "timestamp",
      "open",
      "high",
      "low",
      "close",
      "tick_volume",
      "volume",
      "spread",
      "symbol",
      "timeframe"
   );

   for(int i = 0; i < copied; i++)
   {
      double spread_price = (double)rates[i].spread * point;
      FileWrite(
         handle,
         TimeToString(rates[i].time, TIME_DATE | TIME_SECONDS),
         DoubleToString(rates[i].open, digits),
         DoubleToString(rates[i].high, digits),
         DoubleToString(rates[i].low, digits),
         DoubleToString(rates[i].close, digits),
         (long)rates[i].tick_volume,
         (long)rates[i].real_volume,
         DoubleToString(spread_price, digits),
         InpSymbol,
         EnumToString(InpTimeframe)
      );
   }

   FileFlush(handle);
   FileClose(handle);

   string base_path = InpCommonFolder
      ? TerminalInfoString(TERMINAL_COMMONDATA_PATH) + "\\Files\\"
      : TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files\\";

   PrintFormat("Export complete: %d bars written to %s%s", copied, base_path, InpOutputFile);
   Alert("FX Navigators export complete: ", copied, " bars");
}
