//+------------------------------------------------------------------+
//| FX Navigators - Post-2026H1 XAUUSD H1 Raw Data Exporter          |
//| Acquisition only: no labels, predictions, or engine evaluation.  |
//+------------------------------------------------------------------+
#property copyright "FX Navigators"
#property version   "1.00"
#property script_show_inputs

input string          InpSymbol       = "";  // empty = use chart symbol
input ENUM_TIMEFRAMES InpTimeframe    = PERIOD_H1;
input datetime        InpStart        = D'2026.07.01 00:00:00';
input string          InpFilePrefix   = "FXNavigators_XAUUSD_H1_post_2026H1_raw";
input bool            InpCommonFolder = false;  // false → easier: MQL5/Files under this terminal

const datetime LOCKED_START = D'2026.07.01 00:00:00';


string ExportStamp(const datetime gmt_now)
{
   MqlDateTime parts;
   TimeToStruct(gmt_now, parts);

   return StringFormat(
      "%04d%02d%02dT%02d%02d%02dZ",
      parts.year,
      parts.mon,
      parts.day,
      parts.hour,
      parts.min,
      parts.sec
   );
}


int OutputFlags()
{
   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ;

   if(InpCommonFolder)
      flags |= FILE_COMMON;

   return flags;
}


bool FindLastClosedBarFor(const string symbol, datetime &last_closed)
{
   last_closed = 0;

   for(int attempt = 0; attempt < 20; attempt++)
   {
      ResetLastError();
      last_closed = iTime(
         symbol,
         InpTimeframe,
         1
      );

      if(last_closed > 0)
         return true;

      Sleep(500);
   }

   return false;
}


void WriteMetadata(
   const MqlRates &rates[],
   const int copied,
   const datetime last_closed,
   const string output_file,
   const string metadata_file,
   const datetime server_now,
   const datetime gmt_now,
   const string symbol
)
{
   ResetLastError();

   int handle = FileOpen(
      metadata_file,
      OutputFlags(),
      ','
   );

   if(handle == INVALID_HANDLE)
   {
      PrintFormat(
         "Metadata warning: could not open %s. Error=%d",
         metadata_file,
         GetLastError()
      );
      return;
   }

   long server_minus_gmt = (long)(server_now - gmt_now);

   FileWrite(handle, "key", "value");
   FileWrite(handle, "dataset_role", "UNLABELED_QUARANTINED_RAW_CANDLES");
   FileWrite(handle, "symbol", symbol);
   FileWrite(handle, "timeframe", EnumToString(InpTimeframe));
   FileWrite(handle, "requested_start_server", TimeToString(InpStart, TIME_DATE | TIME_SECONDS));
   FileWrite(handle, "first_bar_server", TimeToString(rates[0].time, TIME_DATE | TIME_SECONDS));
   FileWrite(handle, "first_bar_epoch", (long)rates[0].time);
   FileWrite(handle, "last_closed_bar_server", TimeToString(last_closed, TIME_DATE | TIME_SECONDS));
   FileWrite(handle, "last_closed_bar_epoch", (long)last_closed);
   FileWrite(handle, "rows", copied);
   FileWrite(handle, "raw_file", output_file);
   FileWrite(handle, "account_server", AccountInfoString(ACCOUNT_SERVER));
   FileWrite(handle, "terminal_company", TerminalInfoString(TERMINAL_COMPANY));
   FileWrite(handle, "terminal_name", TerminalInfoString(TERMINAL_NAME));
   FileWrite(handle, "exported_at_server", TimeToString(server_now, TIME_DATE | TIME_SECONDS));
   FileWrite(handle, "exported_at_gmt", TimeToString(gmt_now, TIME_DATE | TIME_SECONDS));
   FileWrite(handle, "server_minus_gmt_seconds_at_export", server_minus_gmt);
   FileWrite(handle, "contains_labels", "false");
   FileWrite(handle, "contains_predictions", "false");
   FileWrite(handle, "engine_version_evaluated", "none");

   FileFlush(handle);
   FileClose(handle);
}


void OnStart()
{
   string symbol = InpSymbol;
   StringTrimLeft(symbol);
   StringTrimRight(symbol);
   if(StringLen(symbol) == 0)
      symbol = _Symbol;

   PrintFormat(
      "Export start: symbol=%s tf=%s start=%s common_folder=%s chart=%s",
      symbol,
      EnumToString(InpTimeframe),
      TimeToString(InpStart, TIME_DATE | TIME_SECONDS),
      InpCommonFolder ? "true" : "false",
      _Symbol
   );

   if(InpTimeframe != PERIOD_H1)
   {
      Print("Export refused: this acquisition script permits only PERIOD_H1.");
      Alert("Export failed: timeframe must be H1");
      return;
   }

   if(InpStart < LOCKED_START)
   {
      PrintFormat(
         "Export refused: start %s precedes locked acquisition boundary %s.",
         TimeToString(InpStart, TIME_DATE | TIME_SECONDS),
         TimeToString(LOCKED_START, TIME_DATE | TIME_SECONDS)
      );
      Alert("Export failed: start date too early");
      return;
   }

   if(!SymbolSelect(symbol, true))
   {
      PrintFormat(
         "Export failed: could not select symbol %s. Error=%d. "
         "Open the XAUUSD chart first, leave InpSymbol empty, or set InpSymbol to the exact Market Watch name.",
         symbol,
         GetLastError()
      );
      Alert("Export failed: bad symbol — see Experts log");
      return;
   }

   // Rebind script inputs that use InpSymbol further below via local `symbol`.
   // CopyRates / iTime need the resolved name.
   datetime last_closed = 0;

   if(!FindLastClosedBarFor(symbol, last_closed))
   {
      PrintFormat(
         "Export failed: could not resolve the latest closed H1 bar for %s. Error=%d. "
         "Scroll the H1 chart to load history, then re-run.",
         symbol,
         GetLastError()
      );
      Alert("Export failed: no H1 history — scroll chart left, re-run");
      return;
   }

   if(last_closed < InpStart)
   {
      PrintFormat(
         "Export stopped: no completed bars exist from %s through %s.",
         TimeToString(InpStart, TIME_DATE | TIME_SECONDS),
         TimeToString(last_closed, TIME_DATE | TIME_SECONDS)
      );
      Alert("Export failed: no bars after 2026.07.01");
      return;
   }

   datetime server_now = TimeTradeServer();
   datetime gmt_now = TimeGMT();

   string stamp = ExportStamp(gmt_now);
   string output_file = InpFilePrefix + "_" + stamp + ".csv";
   string metadata_file = InpFilePrefix + "_" + stamp + ".meta.csv";

   int common_flag = InpCommonFolder ? FILE_COMMON : 0;

   if(
      FileIsExist(output_file, common_flag)
      || FileIsExist(metadata_file, common_flag)
   )
   {
      PrintFormat(
         "Export refused: timestamped output already exists for %s.",
         stamp
      );
      Alert("Export refused: file already exists for this second — wait 1s and re-run");
      return;
   }

   MqlRates rates[];
   ArraySetAsSeries(rates, false);

   int copied = -1;

   for(int attempt = 0; attempt < 20; attempt++)
   {
      ResetLastError();

      copied = CopyRates(
         symbol,
         InpTimeframe,
         InpStart,
         last_closed,
         rates
      );

      if(copied > 0)
         break;

      Sleep(500);
   }

   if(copied <= 0)
   {
      PrintFormat(
         "Export failed: CopyRates returned %d for %s. Error=%d. "
         "Tools → Options → Charts → Max bars in chart = Unlimited, then scroll H1 history.",
         copied,
         symbol,
         GetLastError()
      );
      Alert("Export failed: CopyRates empty — load more H1 history");
      return;
   }

   int handle = FileOpen(
      output_file,
      OutputFlags(),
      ','
   );

   if(handle == INVALID_HANDLE)
   {
      PrintFormat(
         "Export failed: could not open %s. Error=%d",
         output_file,
         GetLastError()
      );
      Alert("Export failed: could not open output file");
      return;
   }

   int digits = (int)SymbolInfoInteger(
      symbol,
      SYMBOL_DIGITS
   );

   double point = SymbolInfoDouble(
      symbol,
      SYMBOL_POINT
   );

   FileWrite(
      handle,
      "timestamp_server",
      "timestamp_epoch",
      "open",
      "high",
      "low",
      "close",
      "tick_volume",
      "volume",
      "spread_price",
      "symbol",
      "timeframe"
   );

   for(int index = 0; index < copied; index++)
   {
      double spread_price = (
         (double)rates[index].spread * point
      );

      FileWrite(
         handle,
         TimeToString(
            rates[index].time,
            TIME_DATE | TIME_SECONDS
         ),
         (long)rates[index].time,
         DoubleToString(rates[index].open, digits),
         DoubleToString(rates[index].high, digits),
         DoubleToString(rates[index].low, digits),
         DoubleToString(rates[index].close, digits),
         (long)rates[index].tick_volume,
         (long)rates[index].real_volume,
         DoubleToString(spread_price, digits),
         symbol,
         EnumToString(InpTimeframe)
      );
   }

   FileFlush(handle);
   FileClose(handle);

   WriteMetadata(
      rates,
      copied,
      last_closed,
      output_file,
      metadata_file,
      server_now,
      gmt_now,
      symbol
   );

   string base_path = InpCommonFolder
      ? TerminalInfoString(TERMINAL_COMMONDATA_PATH) + "\\Files\\"
      : TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files\\";

   PrintFormat(
      "Acquisition complete: %d closed H1 bars written to %s%s",
      copied,
      base_path,
      output_file
   );

   PrintFormat(
      "Metadata written to %s%s",
      base_path,
      metadata_file
   );

   // Also print a Finder/Explorer hint.
   PrintFormat("OPEN THIS FOLDER: %s", base_path);

   Alert(
      "FX Navigators post-2026H1 acquisition complete: ",
      copied,
      " closed bars → ",
      base_path
   );
}
