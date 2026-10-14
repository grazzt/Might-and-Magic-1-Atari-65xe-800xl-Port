; 65XE font reconstruction. The thunk stays visible with the OS enabled;
; no OS routines run, and zero page stays the game's. Called with DMA off.
font_start:
        .export font_source
make_font:
        php
        sei
        lda #0
        sta NMIEN
        tsx
        cpx #$90                ; protect $0100-$017F from our stack
        bcs :+
        jmp font_error
:       ldx #0
font_next:
        txa
        lsr a
        clc
        adc #>FONT
        sta dest+1
        lda rom_high,x
        sta font_source+1
        txa
        lsr a
        lda #0
        ror a                   ; half-page offset from X bit zero
        sta font_source
        sta dest
        stx font_half
        jsr font_read
        ldy #$7F
:       lda $0100,y
        sta (dest),y
        dey
        bpl :-
        ldx font_half
        inx
        cpx #8
        bne font_next
font_done:
        lda #$40
        sta NMIEN
        plp
        rts

font_read:
        ldx #PB_OS
        stx PORTB
        ldy #$7F
font_source = * + 1
:       lda ROMFONT,y
        sta $0100,y
        dey
        bpl :-
        dex
        stx PORTB
        rts
font_end:
