; PitVoice AI – Setup mit Inno Setup (kostenlos, jrsoftware.org)
; Bauen: Doppelklick auf "Setup-bauen.cmd" (braucht Inno Setup 6).
; Das Setup kopiert das Programm, richtet Python ein, lädt die Zusatzpakete und stellt ACC ein.
; Die eigentlichen Einrichtungsschritte macht programm\einrichten.py (gut lesbar, kein verstecktes Skript).

#define AppName "PitVoice AI"
#define AppVersion "1.0.0"
#define PythonVersion "3.13.7"
#define PythonUrl "https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe"

[Setup]
AppId={{7B1E4F2A-5C3D-4E8B-9A61-2D0F7C9E4B13}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=PitVoice AI (Lutz Wagner)
AppPublisherURL=https://pitvoice.com
AppSupportURL=https://pitvoice.com
AppUpdatesURL=https://pitvoice.com/#updates
AppContact=info@pitvoice.com
VersionInfoVersion={#AppVersion}
VersionInfoCompany=PitVoice AI
VersionInfoDescription=PitVoice AI Setup
VersionInfoProductName={#AppName}
VersionInfoCopyright=GPL-3.0, PitVoice AI
DefaultDirName={code:StandardZiel}
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
OutputDir=.
OutputBaseFilename=PitVoice-AI-Setup
SetupIconFile=setup.ico
UninstallDisplayIcon={app}\renningenieur.ico
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
; Dunkles Design wie die App (ab Inno Setup 6.6), Titelleiste ebenfalls dunkel
#if Ver >= EncodeVer(6,6,0)
WizardStyle=modern dark includetitlebar
#else
WizardStyle=modern
#endif
WizardImageFile=bilder\gross.bmp,bilder\gross2.bmp
WizardSmallImageFile=bilder\klein.bmp,bilder\klein2.bmp
; Bilder mit Transparenz (32 Bit): das Flaggen-Logo ohne weißen Kasten
WizardImageAlphaFormat=defined
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
CloseApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
german.SelectLanguageLabel=Wähle die Sprache für die Installation.%n%nSie gilt auch als Start-Sprache von PitVoice AI. Im Programm kannst du sie jederzeit unter Einstellungen ändern.
english.SelectLanguageLabel=Select the language for the installation.%n%nIt is also used as PitVoice AI's starting language. You can change it any time in the program under Settings.

[CustomMessages]
german.Desktop=Verknüpfung auf dem Desktop
english.Desktop=Desktop shortcut
german.Starten=PitVoice AI jetzt starten
english.Starten=Start PitVoice AI now
german.KiTitel=Wie soll die KI laufen?
english.KiTitel=How should the AI run?
german.KiText=Die KI versteht frei gesprochene Fragen und gibt dir Rat. Du kannst das später jederzeit ändern.
english.KiText=The AI understands freely spoken questions and gives you advice. You can change this any time later.
german.Online=Online über Groq (empfohlen): kostenlos, keine FPS-Einbußen, läuft auch auf schwächeren PCs
english.Online=Online via Groq (recommended): free, no FPS loss, runs on weaker PCs too
german.Schluessel=Kostenloser API-Schlüssel (geht auch später im Programm):
english.Schluessel=Free API key (you can also add it later in the program):
german.Holen=Kostenlosen Schlüssel holen (2 Minuten, ohne Kreditkarte)
english.Holen=Get a free key (2 minutes, no credit card)
german.Erkennung=Spracherkennung auch online (entlastet den PC)
english.Erkennung=Speech recognition online too (takes load off the PC)
german.Lokal=Lokal auf diesem PC (nicht empfohlen): langsamer, kostet FPS, braucht 8 GB Grafikkarte und lädt etwa 4 GB
english.Lokal=Locally on this PC (not recommended): slower, costs FPS, needs an 8 GB graphics card and downloads about 4 GB
german.ThemaTitel=Farbthema
english.ThemaTitel=Colour theme
german.ThemaText=Die Farben der Lichter hinter dem Glas. Lässt sich im Programm jederzeit ändern.
english.ThemaText=The colours of the lights behind the glass. You can change it in the program any time.
german.PythonLaden=Python {#PythonVersion} wird geladen (kostenlos, python.org) ...
english.PythonLaden=Downloading Python {#PythonVersion} (free, python.org) ...
german.PythonInstall=Python wird installiert ...
english.PythonInstall=Installing Python ...
german.PythonFehler=Python konnte nicht installiert werden. Bitte Python 3.13 von python.org installieren und das Setup danach noch einmal starten.
english.PythonFehler=Python could not be installed. Please install Python 3.13 from python.org and run the setup again afterwards.
german.SchrittPakete=Zusatzpakete laden (Spracherkennung, Ton, Fenster). Das kann beim ersten Mal ein paar Minuten dauern ...
english.SchrittPakete=Downloading components (speech recognition, audio, window). This can take a few minutes the first time ...
german.SchrittAcc=Assetto Corsa Competizione einstellen ...
english.SchrittAcc=Configuring Assetto Corsa Competizione ...
german.SchrittEinst=Einstellungen speichern ...
english.SchrittEinst=Saving settings ...
german.SchrittStimme=Stimme des Ingenieurs laden (einmalig, etwa 100 MB) ...
english.SchrittStimme=Downloading the engineer's voice (one-time, about 100 MB) ...
german.SchrittOllama=Lokale KI einrichten (Ollama und Modell, etwa 4 GB) ...
english.SchrittOllama=Setting up local AI (Ollama and model, about 4 GB) ...
german.PaketeFehler=Die Zusatzpakete konnten nicht geladen werden. Bitte die Internetverbindung prüfen und das Setup noch einmal starten.%n%nDetails: setup-protokoll.txt im Programmordner.
english.PaketeFehler=The components could not be downloaded. Please check your internet connection and run the setup again.%n%nDetails: setup-protokoll.txt in the program folder.
german.AccWarnung=Die ACC-Einstellungen wurden nicht gefunden. Starte ACC einmal, beende es und führe das Setup danach noch einmal aus.
english.AccWarnung=The ACC settings were not found. Start ACC once, close it and run the setup again afterwards.

[Tasks]
Name: "desktop"; Description: "{cm:Desktop}"

[Files]
Source: "programm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc"

[InstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\deinstallieren.ps1"

[Icons]
Name: "{userprograms}\PitVoice AI"; Filename: "{code:PythonW}"; Parameters: """{app}\acc_app.py"""; WorkingDir: "{app}"; IconFilename: "{app}\renningenieur.ico"; Comment: "PitVoice AI"
Name: "{userdesktop}\PitVoice AI"; Filename: "{code:PythonW}"; Parameters: """{app}\acc_app.py"""; WorkingDir: "{app}"; IconFilename: "{app}\renningenieur.ico"; Comment: "PitVoice AI"; Tasks: desktop

[Run]
Filename: "{code:PythonW}"; Parameters: """{app}\acc_app.py"""; WorkingDir: "{app}"; Description: "{cm:Starten}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\setup-protokoll.txt"

[Code]
const
  UNINSTALL_SCHLUESSEL = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\';

var
  KiSeite, ThemaSeite: TWizardPage;
  OnlineKnopf, LokalKnopf: TNewRadioButton;
  SchluesselFeld: TPasswordEdit;
  ErkennungHaken: TNewCheckBox;
  ThemaKnoepfe: array[0..7] of TNewRadioButton;
  PythonExe: String;
  DownloadSeite: TDownloadWizardPage;

function ThemaId(I: Integer): String;
begin
  case I of
    0: Result := 'kupfer';
    1: Result := 'gold';
    2: Result := 'petrol';
    3: Result := 'eis';
    4: Result := 'silber';
    5: Result := 'klassik';
    6: Result := 'strecke';
  else
    Result := 'nacht';
  end;
end;

function ThemaName(I: Integer): String;
var
  De: Boolean;
begin
  De := ActiveLanguage = 'german';
  case I of
    0: if De then Result := 'Orange & Kupfer' else Result := 'Orange & copper';
    1: if De then Result := 'Gold & Nachtblau' else Result := 'Gold & midnight';
    2: if De then Result := 'Petrol & Blau' else Result := 'Petrol & blue';
    3: if De then Result := 'Eisblau & Gold' else Result := 'Ice blue & gold';
    4: if De then Result := 'Silber & Blau' else Result := 'Silver & blue';
    5: if De then Result := 'Orange & Lila' else Result := 'Orange & purple';
    6: if De then Result := 'Grün & Rot' else Result := 'Green & red';
  else
    if De then Result := 'Ganz dunkel' else Result := 'All dark';
  end;
end;

{ Farben als $BBGGRR (Windows-Reihenfolge) }
function ThemaFarbe(I, Nr: Integer): Integer;
begin
  case I of
    0: if Nr = 1 then Result := $1F8AFF else Result := $2A56B5;
    1: if Nr = 1 then Result := $20B0FF else Result := $FF4B1F;
    2: if Nr = 1 then Result := $A6B512 else Result := $FF5624;
    3: if Nr = 1 then Result := $F5A93F else Result := $20B0FF;
    4: if Nr = 1 then Result := $C8B39F else Result := $FF6B2F;
    5: if Nr = 1 then Result := $1F8AFF else Result := $FF5B6D;
    6: if Nr = 1 then Result := $6CC219 else Result := $2A33E5;
  else
    if Nr = 1 then Result := $201B1A else Result := $332C2A;
  end;
end;

{ ---------------------------------------------------------------- Zielordner }
function HatProgramm(Ordner: String): Boolean;
begin
  Result := FileExists(AddBackslash(Ordner) + 'acc_app.py');
end;

function StandardZiel(Param: String): String;
begin
  { Eine vorhandene Installation wird aktualisiert, sonst kommt PitVoice in den Benutzerordner }
  if HatProgramm(ExpandConstant('{%USERPROFILE}\PitVoice-AI')) then Result := ExpandConstant('{%USERPROFILE}\PitVoice-AI')
  else if HatProgramm(ExpandConstant('{%USERPROFILE}\RaceMate-AI')) then Result := ExpandConstant('{%USERPROFILE}\RaceMate-AI')
  else if HatProgramm('C:\ACC-Renningenieur') then Result := 'C:\ACC-Renningenieur'
  else if HatProgramm(ExpandConstant('{%USERPROFILE}\ACC-Renningenieur')) then Result := ExpandConstant('{%USERPROFILE}\ACC-Renningenieur')
  else Result := ExpandConstant('{%USERPROFILE}\PitVoice-AI');
end;

{ ---------------------------------------------------------------- Python }
function PythonFinden: String;
var
  Pfad: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, 'Software\Python\PythonCore\3.13\InstallPath', 'ExecutablePath', Pfad) and FileExists(Pfad) then
  begin
    Result := Pfad;
    exit;
  end;
  if RegQueryStringValue(HKLM, 'Software\Python\PythonCore\3.13\InstallPath', 'ExecutablePath', Pfad) and FileExists(Pfad) then
  begin
    Result := Pfad;
    exit;
  end;
  Pfad := ExpandConstant('{localappdata}\Programs\Python\Python313\python.exe');
  if FileExists(Pfad) then begin Result := Pfad; exit; end;
  Pfad := ExpandConstant('{localappdata}\Python\pythoncore-3.13-64\python.exe');
  if FileExists(Pfad) then begin Result := Pfad; exit; end;
  Pfad := ExpandConstant('{commonpf64}\Python313\python.exe');
  if FileExists(Pfad) then begin Result := Pfad; exit; end;
end;

function PythonW(Param: String): String;
begin
  Result := ExtractFilePath(PythonExe) + 'pythonw.exe';
  if not FileExists(Result) then Result := PythonExe;
end;

{ ---------------------------------------------------------------- Seiten }
procedure SchluesselHolen(Sender: TObject);
var
  Fehler: Integer;
begin
  ShellExec('open', 'https://console.groq.com/keys', '', '', SW_SHOWNORMAL, ewNoWait, Fehler);
end;

procedure KiArtGewechselt(Sender: TObject);
begin
  SchluesselFeld.Enabled := OnlineKnopf.Checked;
  ErkennungHaken.Enabled := OnlineKnopf.Checked;
end;

function VorhandenesThema: Integer;
var
  Inhalt: AnsiString;
  I: Integer;
begin
  Result := 0;
  if LoadStringFromFile(AddBackslash(StandardZiel('')) + 'einstellungen.json', Inhalt) then
    for I := 0 to 7 do
      if Pos('"thema": "' + ThemaId(I) + '"', String(Inhalt)) > 0 then Result := I;
end;

procedure SeitenAnlegen;
var
  Text, Link: TNewStaticText;
  I, Y, Gewaehlt: Integer;
  Feld1, Feld2: TPanel;
begin
  { KI }
  KiSeite := CreateCustomPage(wpSelectTasks, CustomMessage('KiTitel'), CustomMessage('KiText'));

  OnlineKnopf := TNewRadioButton.Create(KiSeite);
  OnlineKnopf.Parent := KiSeite.Surface;
  OnlineKnopf.Caption := CustomMessage('Online');
  OnlineKnopf.Top := 0;
  OnlineKnopf.Width := KiSeite.SurfaceWidth;
  OnlineKnopf.Height := ScaleY(20);
  OnlineKnopf.Checked := True;
  OnlineKnopf.OnClick := @KiArtGewechselt;

  Text := TNewStaticText.Create(KiSeite);
  Text.Parent := KiSeite.Surface;
  Text.Caption := CustomMessage('Schluessel');
  Text.Left := ScaleX(18);
  Text.Top := ScaleY(32);

  SchluesselFeld := TPasswordEdit.Create(KiSeite);
  SchluesselFeld.Parent := KiSeite.Surface;
  SchluesselFeld.Left := ScaleX(18);
  SchluesselFeld.Top := ScaleY(52);
  SchluesselFeld.Width := KiSeite.SurfaceWidth - ScaleX(18);

  Link := TNewStaticText.Create(KiSeite);
  Link.Parent := KiSeite.Surface;
  Link.Caption := CustomMessage('Holen');
  Link.Left := ScaleX(18);
  Link.Top := ScaleY(80);
  Link.Cursor := crHand;
  Link.Font.Color := clHighlight;
  Link.Font.Style := [fsUnderline];
  Link.OnClick := @SchluesselHolen;

  ErkennungHaken := TNewCheckBox.Create(KiSeite);
  ErkennungHaken.Parent := KiSeite.Surface;
  ErkennungHaken.Caption := CustomMessage('Erkennung');
  ErkennungHaken.Left := ScaleX(18);
  ErkennungHaken.Top := ScaleY(106);
  ErkennungHaken.Width := KiSeite.SurfaceWidth - ScaleX(18);
  ErkennungHaken.Height := ScaleY(20);
  ErkennungHaken.Checked := True;

  LokalKnopf := TNewRadioButton.Create(KiSeite);
  LokalKnopf.Parent := KiSeite.Surface;
  LokalKnopf.Caption := CustomMessage('Lokal');
  LokalKnopf.Top := ScaleY(150);
  LokalKnopf.Width := KiSeite.SurfaceWidth;
  LokalKnopf.Height := ScaleY(34);
  LokalKnopf.OnClick := @KiArtGewechselt;

  { Farbthema }
  ThemaSeite := CreateCustomPage(KiSeite.ID, CustomMessage('ThemaTitel'), CustomMessage('ThemaText'));
  Gewaehlt := VorhandenesThema;
  for I := 0 to 7 do
  begin
    Y := ScaleY(4 + I * 26);
    Feld1 := TPanel.Create(ThemaSeite);
    Feld1.Parent := ThemaSeite.Surface;
    Feld1.Left := 0;
    Feld1.Top := Y;
    Feld1.Width := ScaleX(14);
    Feld1.Height := ScaleY(18);
    Feld1.BevelOuter := bvNone;
    Feld1.Color := ThemaFarbe(I, 1);
    Feld2 := TPanel.Create(ThemaSeite);
    Feld2.Parent := ThemaSeite.Surface;
    Feld2.Left := ScaleX(14);
    Feld2.Top := Y;
    Feld2.Width := ScaleX(14);
    Feld2.Height := ScaleY(18);
    Feld2.BevelOuter := bvNone;
    Feld2.Color := ThemaFarbe(I, 2);

    ThemaKnoepfe[I] := TNewRadioButton.Create(ThemaSeite);
    ThemaKnoepfe[I].Parent := ThemaSeite.Surface;
    ThemaKnoepfe[I].Caption := ThemaName(I);
    ThemaKnoepfe[I].Left := ScaleX(40);
    ThemaKnoepfe[I].Top := Y;
    ThemaKnoepfe[I].Width := ThemaSeite.SurfaceWidth - ScaleX(40);
    ThemaKnoepfe[I].Height := ScaleY(18);
    ThemaKnoepfe[I].Checked := I = Gewaehlt;
  end;
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  SeitenAnlegen;
  DownloadSeite := CreateDownloadPage(SetupMessage(msgWizardPreparing), CustomMessage('PythonLaden'), @OnDownloadProgress);
end;

function PythonInstallieren: Boolean;
var
  Code: Integer;
  Installer: String;
begin
  Result := False;
  DownloadSeite.Clear;
  DownloadSeite.Add('{#PythonUrl}', 'python-installer.exe', '');
  DownloadSeite.Show;
  try
    try
      DownloadSeite.Download;
      Installer := ExpandConstant('{tmp}\python-installer.exe');
      DownloadSeite.SetText(CustomMessage('PythonInstall'), '');
      DownloadSeite.ProgressBar.Style := npbstMarquee;
      if Exec(Installer, '/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_pip=1 Include_tcltk=1 Shortcuts=0',
              '', SW_HIDE, ewWaitUntilTerminated, Code) then
      begin
        PythonExe := PythonFinden;
        Result := PythonExe <> '';
      end;
    except
      Log('Python-Download: ' + GetExceptionMessage);
    end;
  finally
    DownloadSeite.ProgressBar.Style := npbstNormal;
    DownloadSeite.Hide;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Code: Integer;
begin
  Result := True;
  if CurPageID = wpReady then
  begin
    PythonExe := PythonFinden;
    if PythonExe = '' then
    begin
      if not PythonInstallieren then
      begin
        MsgBox(CustomMessage('PythonFehler'), mbError, MB_OK);
        ShellExec('open', 'https://www.python.org/downloads/', '', '', SW_SHOWNORMAL, ewNoWait, Code);
        Result := False;
      end;
    end;
  end;
end;

{ ---------------------------------------------------------------- Einrichten nach dem Kopieren }
function Schritt(Meldung, Argumente: String): Integer;
var
  Code: Integer;
begin
  WizardForm.StatusLabel.Caption := Meldung;
  WizardForm.FilenameLabel.Caption := '';
  WizardForm.ProgressGauge.Style := npbstMarquee;
  if not Exec(PythonExe, '"' + ExpandConstant('{app}\einrichten.py') + '" ' + Argumente,
              ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then
    Code := 1;
  Log('einrichten.py ' + Argumente + ' -> ' + IntToStr(Code));
  Result := Code;
end;

procedure AltesAufraeumen;
begin
  RegDeleteKeyIncludingSubkeys(HKCU, UNINSTALL_SCHLUESSEL + 'PitVoice-AI');
  RegDeleteKeyIncludingSubkeys(HKCU, UNINSTALL_SCHLUESSEL + 'RaceMate-AI');
  RegDeleteKeyIncludingSubkeys(HKCU, UNINSTALL_SCHLUESSEL + 'ACC-Renningenieur');
  DeleteFile(ExpandConstant('{userdesktop}\RaceMate AI.lnk'));
  DeleteFile(ExpandConstant('{userdesktop}\ACC Renningenieur.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\RaceMate AI.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\ACC Renningenieur.lnk'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  I: Integer;
  Thema, Sprache, Ki, Erkennung, SchluesselDatei: String;
begin
  if CurStep <> ssPostInstall then exit;
  AltesAufraeumen;
  if ActiveLanguage = 'english' then Sprache := 'en' else Sprache := 'de';
  Thema := 'kupfer';
  for I := 0 to 7 do
    if ThemaKnoepfe[I].Checked then Thema := ThemaId(I);
  if LokalKnopf.Checked then Ki := 'lokal' else Ki := 'online';
  if ErkennungHaken.Checked then Erkennung := '1' else Erkennung := '0';
  { Den Schlüssel nicht auf die Befehlszeile schreiben, sondern kurz in eine Datei, die einrichten.py sofort löscht }
  SchluesselDatei := ExpandConstant('{tmp}\schluessel.txt');
  SaveStringToFile(SchluesselDatei, Trim(SchluesselFeld.Text), False);

  if Schritt(CustomMessage('SchrittPakete'), 'pakete') <> 0 then
    MsgBox(CustomMessage('PaketeFehler'), mbError, MB_OK);
  if Schritt(CustomMessage('SchrittAcc'), 'acc') = 2 then
    MsgBox(CustomMessage('AccWarnung'), mbInformation, MB_OK);
  Schritt(CustomMessage('SchrittEinst'), 'einstellungen --sprache ' + Sprache + ' --ki ' + Ki + ' --erkennung ' + Erkennung +
          ' --thema ' + Thema + ' --schluessel-datei "' + SchluesselDatei + '"');
  Schritt(CustomMessage('SchrittStimme'), 'stimme --sprache ' + Sprache);
  if Ki = 'lokal' then
    Schritt(CustomMessage('SchrittOllama'), 'ollama');
  DeleteFile(SchluesselDatei);
  WizardForm.ProgressGauge.Style := npbstNormal;
end;
