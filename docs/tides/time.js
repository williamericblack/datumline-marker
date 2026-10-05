/* TIDES dates. Data writes historical dates as "YYYY", "YYYY-MM" or "YYYY-MM-DD";
 * BC dates carry a leading minus ("-0216-08-02" is 2 Aug 216 BC). There is no year 0:
 * 1 BC is followed by AD 1, so BC year n is astronomical year 1 - n.
 */
(function () {
  "use strict";
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function parse(s) {
    const neg = s[0] === "-", t = neg ? s.slice(1) : s;
    const y = +t.slice(0, 4), m = t.length > 5 ? +t.slice(5, 7) - 1 : 0, day = t.length > 8 ? +t.slice(8, 10) : 1;
    const D = new Date(Date.UTC(2000, m, day));
    D.setUTCFullYear(neg ? 1 - y : y); // setUTCFullYear keeps years 0-99 literal; Date.UTC would map them to 19xx
    return D.getTime();
  }
  // bc: true when the surrounding story crosses into BC, so AD years get an explicit "AD".
  function year(t, bc) {
    const y = new Date(t).getUTCFullYear();
    return y <= 0 ? `${1 - y} BC` : bc && y < 1000 ? `AD ${y}` : String(y);
  }
  function label(s, bc) {
    const t = parse(s), D = new Date(t), y = year(t, bc);
    const body = s[0] === "-" ? s.slice(1) : s;
    return body.length > 8 ? `${D.getUTCDate()} ${MON[D.getUTCMonth()]} ${y}` : body.length > 5 ? `${MON[D.getUTCMonth()]} ${y}` : y;
  }
  window.TIDES_TIME = { parse, year, label, MON };
})();
