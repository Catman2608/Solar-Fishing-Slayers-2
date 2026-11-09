;====================================================================================================;
;
;   Solar Fishing Slayers 2 Macro v2026.11.1
;   Build: September 7th
;
;   LICENSE: GNU GENERAL PUBLIC LICENSE v3.0
;   Copyright (C) 2026 Catman2608
;
;   This program is free software: you can redistribute it and/or modify
;   it under the terms of the GNU General Public License as published by
;   the Free Software Foundation, either version 3 of the License, or
;   (at your option) any later version.
;
;   This program is distributed in the hope that it will be useful,
;   but WITHOUT ANY WARRANTY; without even the implied warranty of
;   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
;   GNU General Public License for more details.
;
;   You should have received a copy of the GNU General Public License
;   along with this program. If not, see <https://www.gnu.org/licenses/>.
;
;   SOURCE CODE
;     Official source code repository: (Insert source code repository when complete)
;
;   PORTIONS FROM OTHER PROJECTS
;     (Insert portions from other projects here)
;     is adapted from (Insert product here) by (Insert author here).
;       Source:  (Insert source here)
;     Those portions remain subject to (Insert author here)'s own terms, which permit sharing
;     modifications with attribution. The restrictions above apply to Catman2608's original work
;     and cannot and do not override (Insert author here)'s terms for their part.
;
;     Changes made to that method in this macro: (Insert here)
;
;   NO WARRANTY
;     This program is provided "as is", without warranty of any kind.
;     See the GNU General Public License v3.0 for details.
;
;     Automating a game may breach its rules.
;     You use this at your own risk, and the author accepts no responsibility for any
;     consequence to your account.
;
;====================================================================================================;

; Initialization
#SingleInstance Force
FileEncoding, UTF-8
setkeydelay, -1
setmousedelay, -1
setbatchlines, -1
SetTitleMatchMode 2

CoordMode, ToolTip, Relative
CoordMode, Pixel, Relative
CoordMode, Mouse, Relative

; GUI (0xRRGGBB)

Gui, +Resize +MinSize
Gui, Color, 0x1D1D1D
Gui, Font, s13 cFFFFFF Bold, Segoe UI
Gui, Add, Text, x30 y10, Solar FIshing Slayers 2
Gui, Font, s9 cFFFFFF Norm, Segoe UI
Gui, Add, Tab2, x20 y40 w650 h570, Main|Advanced|About

; Top Bar

Gui, Tab, 
Gui, Add, Text, x180 y15, Buy bait -> cast -> track - coords follow Roblox

; Main tab
Gui, Tab, Main
Gui, Font, s9 c0x90EE90 Bold
Gui, Add, Text, x40 y80, Main

Gui, Font, s9 c0x90EE90 Bold
Gui, Add, GroupBox, x40 y110 w300 h130, Hotkey Settings
Gui, Font, s9 cWhite Norm

Gui, Add, Text, x60 y130, Start Key:
Gui, Add, Edit, x220 y130 w100 vStartKey cBlack, F5

Gui, Add, Text, x60 y160, Stop Key:
Gui, Add, Edit, x220 y160 w100 vStopKey cBlack, F7

Gui, Font, s9 c0x90EE90 Bold
Gui, Add, GroupBox, x350 y110 w300 h130, Area Settings
Gui, Font, s9 cWhite Norm

Gui, Add, Text, x370 y130, Fishing Rod Key:
Gui, Add, Edit, x530 y130 w100 vFishingRodKey cBlack, 1

Gui, Add, Text, x370 y160, Equipment Bag Key:
Gui, Add, Edit, x530 y160 w100 vEquipmentBagKey cBlack, 2

Gui, Font, s9 c0x90EE90 Bold
Gui, Add, Text, x40 y250, CYCLE ORDER
Gui, Add, GroupBox, x40 y270 w300 h300, 1 - Buy bait
Gui, Add, GroupBox, x350 y270 w300 h120, 2 - Collect fish
Gui, Add, GroupBox, x350 y400 w300 h90, 3 - Cast
Gui, Add, GroupBox, x350 y500 w300 h90, 4 - Minigame
Gui, Font, s9 cWhite Norm

Gui, Add, Text, x60 y300, Auto Buy Bait:
Gui, Add, Checkbox, x220 y300 vAutoBuyBait, Enable

Gui, Add, Text, x60 y330, Amount:
Gui, Add, Edit, x220 y330 w100 vBuyBaitAmount cBlack, 10

Gui, Add, Text, x60 y360, Got any bait?:
Gui, Add, Edit, x220 y360 w100 vGotAnyBait cBlack, 0.666 0.839

Gui, Add, Text, x60 y390, Center of textbox:
Gui, Add, Edit, x220 y390 w100 vCenterOfTextbox cBlack, 0.5 0.853

Gui, Add, Text, x60 y420, Bait:
Gui, Add, Edit, x220 y420 w100 vBait cBlack, 0.34 0.652

Gui, Add, Text, x60 y450, Increment Arrow:
Gui, Add, Edit, x220 y450 w100 vIncrementArrow cBlack, 0.319 0.629

Gui, Add, Text, x60 y480, Buy the selection:
Gui, Add, Edit, x220 y480 w100 vBuyTheSelection cBlack, 0.67 0.821

Gui, Add, Text, x60 y510, Deal:
Gui, Add, Edit, x220 y510 w100 vDeal cBlack, 0.666 0.838

Gui, Add, Text, x60 y540, Close:
Gui, Add, Edit, x220 y540 w100 vClose cBlack, 0.667 0.872

Gui, Add, Text, x370 y300, Delay before collect (ms):
Gui, Add, Edit, x530 y300 w100 vDelayBeforeCollect cBlack, 2000

Gui, Add, Text, x370 y330, Hold (ms):
Gui, Add, Edit, x530 y330 w100 vHold cBlack, 3000

Gui, Add, Text, x370 y360, Hold Position:
Gui, Add, Edit, x530 y360 w100 vHoldPosition cBlack, 0.51 0.403

Gui, Add, Checkbox, x370 y420 vCastOutside, Cast outside top-left of scan area

Gui, Add, Text, x370 y450, Cast Point:
Gui, Add, Edit, x530 y450 w100 vCastPoint cBlack, 0.717 0.267

Gui, Add, Text, x370 y520, Modify the scan area using the Area Preview. Track 
Gui, Add, Text, x370 y540, starts when white app fall cast after the Advanced 
Gui, Add, Text, x370 y560, timeout with no white. Fine-tune FPS / track / delays
Gui, Add, Text, x370 y580, in the Advanced tab.

; Advanced tab
Gui, Tab, Advanced
Gui, Font, s9 c0x87CEEB Bold
Gui, Add, Text, x40 y80, Automation Settings

Gui, Font, s9 c0x87CEEB Bold
Gui, Add, GroupBox, x40 y110 w300 h250, Basic Options
Gui, Font, s9 cWhite Norm


; About Tab
Gui, Tab, About
Gui, Font, s9 c0xFFFFFF Bold
Gui, Add, Text, x40 y80, About

; About section
Gui, Font, s9 cFFFFFF Bold
Gui, Add, GroupBox, x40 y110 w600 h220, About this macro
Gui, Font, s9 cFFFFFF Norm

Gui, Add, Picture, x60 y130 w48 h48, % mainDir "images\\Catman.png"
Gui, Font, s9 cFFD700 Bold
Gui, Add, Text, x120 y130 w350, Catman2608
Gui, Font, s9 cFFC0CB Bold
Gui, Add, Text, x120 y150 w350, Creator, Design and Development.
Gui, Font, s9 cFFFFFF Norm

Gui, Add, Picture, x60 y190 w48 h48, % mainDir "images\\AsphaltCake.png"
Gui, Font, s9 cFFD700 Bold
Gui, Add, Text, x120 y190 w350, Asphalt Cake
Gui, Font, s9 cFFC0CB Bold
Gui, Add, Text, x120 y210 w350, Precision/Lines mode control method, adapted from IRUS IDIOTPROOF/IRUS COMET
Gui, Font, s9 cFFFFFF Norm

; Disclaimer section
Gui, Font, s9 cFF4444 Bold
Gui, Add, Text, x60 y250 w550, IMPORTANT DISCLAIMER: 
Gui, Font, s9 cFFFFFF Norm
Gui, Add, Text, x60 y270 w550, Any person claiming to be part of this project or its development, other than the people above
Gui, Add, Text, x60 y290 w550, is most likely lying. Be cautious of fake contributors or impersonators.

; Resources section
Gui, Font, s9 cFFFFFF Bold
Gui, Add, GroupBox, x40 y350 w600 h180, Resources
Gui, Font, s9 cFFFFFF Norm

; Links with proper spacing
Gui, Add, Link, x60 y370, <a href="https://discord.com/invite/aMZY8yrF8r">Join Solar Macros Discord Server</a>
Gui, Add, Link, x60 y400, <a href="https://www.youtube.com/@HexaTitanGaming/">Catman's YouTube Channel</a>
Gui, Add, Link, x60 y430, <a href="https://catman2608.github.io/PyWare-Backend/">Catman's Solar Macro Website</a>
Gui, Add, Link, x60 y460, <a href="https://github.com/Catman2608/Solar-Fishing-Lite">Source Code</a>
Gui, Add, Link, x60 y490, <a href="https://docs.google.com/document/d/1WwWWMR-eN-R-GO42IioToHpWTgiXkLoiNE_4NeE-GsU">Upcoming Features</a>
Gui, Add, Link, x60 y520, <a href="https://docs.google.com/document/d/1ZTDFi4jwSnJE1jq3bT1yNnnX3V-ohEOvXNOm6P1dPNU/edit?tab=t.0">Settings Guide</a>

Gui, Add, Link, x370 y370, <a href="https://discord.com/invite/vKVBbyfHTD">Join Asphalt Cake's Discord Server</a>
Gui, Add, Link, x370 y400, <a href="https://www.youtube.com/@AsphaltCake/">Asphalt Cake's YouTube Channel</a>

; Show Window and load settings
Gui, Show
return
